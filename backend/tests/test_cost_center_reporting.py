"""Cost Center Reporting — the reason Cost Centers exist: knowing which
revenue/expense (or any) account belongs to which cost center. Covers the
optional cost-center filter added to General Ledger and Income Statement,
and the new dedicated Cost Center Report endpoint (every account the cost
center touched, with a non-zero balance, in the period)."""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="CCR"):
    payload = {
        "tenant_legal_name": f"{label} Holding",
        "company_legal_name": f"{label} Trading Co.",
        "company_legal_name_ar": f"{label} Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": f"{label} Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201, boot_resp.text
    company_id = boot_resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return company_id, headers


async def _get_account_id(client, headers, code: str) -> str:
    resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    return next(a["id"] for a in resp.json() if a["code"] == code)


async def _create_cost_center(client, headers, name="Marketing") -> dict:
    resp = await client.post("/api/v1/accounting/cost-centers", headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _post_je(client, headers, entry_date: str, lines: list[dict]) -> str:
    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={"journal_code": "GEN", "entry_date": entry_date, "lines": lines},
    )
    assert create_resp.status_code == 201, create_resp.text
    entry_id = create_resp.json()["id"]
    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert post_resp.status_code == 200, post_resp.text
    return entry_id


async def _seed_two_cost_centers_activity(client, headers):
    """Two cost centers, each with its own revenue and expense lines, plus
    one line with no cost center at all -- proving the filter is precise
    (nothing bleeds between cost centers or into the "no cost center" bucket)."""
    cash = await _get_account_id(client, headers, "1100")
    capital = await _get_account_id(client, headers, "3100")
    revenue = await _get_account_id(client, headers, "4100")
    opex = await _get_account_id(client, headers, "5200")

    store1 = await _create_cost_center(client, headers, "Store 1")
    store2 = await _create_cost_center(client, headers, "Store 2")

    await _post_je(  # capital injection, no cost center
        client, headers, "2026-06-01", [
            {"account_id": cash, "debit": 10000, "credit": 0},
            {"account_id": capital, "debit": 0, "credit": 10000},
        ],
    )
    await _post_je(  # Store 1 revenue
        client, headers, "2026-06-05", [
            {"account_id": cash, "debit": 1000, "credit": 0, "cost_center_id": store1["id"]},
            {"account_id": revenue, "debit": 0, "credit": 1000, "cost_center_id": store1["id"]},
        ],
    )
    await _post_je(  # Store 1 expense
        client, headers, "2026-06-06", [
            {"account_id": opex, "debit": 200, "credit": 0, "cost_center_id": store1["id"]},
            {"account_id": cash, "debit": 0, "credit": 200, "cost_center_id": store1["id"]},
        ],
    )
    await _post_je(  # Store 2 revenue only
        client, headers, "2026-06-07", [
            {"account_id": cash, "debit": 500, "credit": 0, "cost_center_id": store2["id"]},
            {"account_id": revenue, "debit": 0, "credit": 500, "cost_center_id": store2["id"]},
        ],
    )
    return {
        "cash": cash, "revenue": revenue, "opex": opex,
        "store1": store1, "store2": store2,
    }


# --- General Ledger: cost-center awareness -----------------------------------


async def test_general_ledger_line_exposes_cost_center(client):
    _, headers = await _bootstrap_and_login(client, "GlExpose")
    ctx = await _seed_two_cost_centers_activity(client, headers)

    resp = await client.get(
        "/api/v1/accounting/reports/general-ledger",
        headers=headers,
        params={"account_id": ctx["cash"], "date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200
    lines = resp.json()["lines"]
    assert len(lines) == 4
    tagged = {line_["cost_center_id"] for line_ in lines if line_["cost_center_id"]}
    assert tagged == {ctx["store1"]["id"], ctx["store2"]["id"]}
    store1_line = next(line_ for line_ in lines if line_["cost_center_id"] == ctx["store1"]["id"])
    assert store1_line["cost_center_name"] == "Store 1"


async def test_general_ledger_filters_by_cost_center(client):
    _, headers = await _bootstrap_and_login(client, "GlFilter")
    ctx = await _seed_two_cost_centers_activity(client, headers)

    resp = await client.get(
        "/api/v1/accounting/reports/general-ledger",
        headers=headers,
        params={
            "account_id": ctx["cash"],
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "cost_center_id": ctx["store1"]["id"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # Opening balance must also respect the filter: nothing before 2026-06-01
    # was tagged Store 1, so opening is 0, not the unfiltered 10000.
    assert body["opening_balance"] == "0.0000"
    assert len(body["lines"]) == 2  # the +1000 and -200 Store 1 cash lines only
    assert all(line_["cost_center_id"] == ctx["store1"]["id"] for line_ in body["lines"])
    assert body["closing_balance"] == "800.0000"


# --- Income Statement: cost-center filter -------------------------------------


async def test_income_statement_filters_by_cost_center(client):
    _, headers = await _bootstrap_and_login(client, "IsFilter")
    ctx = await _seed_two_cost_centers_activity(client, headers)

    resp = await client.get(
        "/api/v1/accounting/reports/income-statement",
        headers=headers,
        params={
            "date_from": "2026-06-01", "date_to": "2026-06-30",
            "cost_center_id": ctx["store1"]["id"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["revenue_total"] == "1000.0000"
    assert body["opex_total"] == "200.0000"
    assert body["net_income"] == "800.0000"


async def test_income_statement_unfiltered_still_sums_all_cost_centers(client):
    """Regression: the existing (no cost_center_id) call must keep summing
    across every cost center, exactly as before this stage."""
    _, headers = await _bootstrap_and_login(client, "IsUnfiltered")
    ctx = await _seed_two_cost_centers_activity(client, headers)

    resp = await client.get(
        "/api/v1/accounting/reports/income-statement",
        headers=headers,
        params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["revenue_total"] == "1500.0000"  # Store 1 (1000) + Store 2 (500)
    assert body["opex_total"] == "200.0000"


# --- Cost Center Report --------------------------------------------------------


async def test_cost_center_report_lists_only_accounts_with_balance(client):
    _, headers = await _bootstrap_and_login(client, "CcReport")
    ctx = await _seed_two_cost_centers_activity(client, headers)

    resp = await client.get(
        f"/api/v1/accounting/reports/cost-center/{ctx['store1']['id']}",
        headers=headers,
        params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cost_center"]["id"] == ctx["store1"]["id"]
    account_codes = {row["account_code"] for row in body["accounts"]}
    # Cash, Revenue, OpEx all touched Store 1 and each nets non-zero.
    assert account_codes == {"1100", "4100", "5200"}
    assert body["revenue_total"] == "1000.0000"
    assert body["expense_total"] == "200.0000"
    assert body["net_result"] == "800.0000"

    cash_row = next(r for r in body["accounts"] if r["account_code"] == "1100")
    assert cash_row["balance"] == "800.0000"  # +1000 - 200, debit-normal


async def test_cost_center_report_excludes_other_cost_centers_activity(client):
    _, headers = await _bootstrap_and_login(client, "CcReportIso")
    ctx = await _seed_two_cost_centers_activity(client, headers)

    resp = await client.get(
        f"/api/v1/accounting/reports/cost-center/{ctx['store2']['id']}",
        headers=headers,
        params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200
    body = resp.json()
    account_codes = {row["account_code"] for row in body["accounts"]}
    assert account_codes == {"1100", "4100"}  # no OpEx -- that was only Store 1
    assert body["revenue_total"] == "500.0000"
    assert body["expense_total"] == "0.0000"


async def test_cost_center_report_unknown_cost_center_404(client):
    _, headers = await _bootstrap_and_login(client, "CcReport404")
    resp = await client.get(
        "/api/v1/accounting/reports/cost-center/00000000-0000-0000-0000-000000000099",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 404


async def test_cost_center_report_cross_company_rejected(client):
    _, headers_a = await _bootstrap_and_login(client, "CcReportIsoA")
    _, headers_b = await _bootstrap_and_login(client, "CcReportIsoB")
    cc_a = await _create_cost_center(client, headers_a, "Company A Only")

    resp = await client.get(
        f"/api/v1/accounting/reports/cost-center/{cc_a['id']}",
        headers=headers_b,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 404


async def test_cost_center_report_requires_permission(client):
    resp = await client.get(
        "/api/v1/accounting/reports/cost-center/00000000-0000-0000-0000-000000000099",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 401
