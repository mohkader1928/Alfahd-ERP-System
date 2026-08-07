"""Integration smoke test for Backend M1 — Accounting.

Exercises UC-ACC-01/02 end to end: company registration triggers CoA
seeding via the CompanyRegistered domain event (Phase 8 §3/§7), then the
full draft -> balance-check -> post -> reverse -> trial-balance cycle,
per FR-ACC-002..009.
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, *, valuation_method="average"):
    payload = {
        "tenant_legal_name": "Acc Test Holding",
        "company_legal_name": "Acc Test Trading Co.",
        "company_legal_name_ar": "Acc Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": valuation_method,
        "admin_email": unique_email(),
        "admin_full_name": "Acc Test Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201
    company_id = boot_resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return company_id, headers


async def _get_account_id(client, headers, code: str) -> str:
    resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    accounts = resp.json()
    return next(a["id"] for a in accounts if a["code"] == code)


async def test_company_registration_seeds_default_chart_of_accounts(client):
    _, headers = await _bootstrap_and_login(client)

    resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    assert resp.status_code == 200
    accounts = resp.json()
    codes = {a["code"] for a in accounts}
    assert {"1000", "1100", "2100", "3100", "4100", "5100"}.issubset(codes)


async def test_unbalanced_journal_entry_rejected(client):
    _, headers = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")

    resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-01-01",
            "lines": [
                {"account_id": cash_id, "debit": 1000, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 500},
            ],
        },
    )
    assert resp.status_code == 422


async def test_balanced_entry_post_and_trial_balance(client):
    _, headers = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")

    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-01-15",
            "lines": [
                {"account_id": cash_id, "debit": 1000, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 1000},
            ],
        },
    )
    assert create_resp.status_code == 201
    entry_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "draft"

    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert post_resp.status_code == 200
    assert post_resp.json()["status"] == "posted"

    repost_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert repost_resp.status_code == 409

    tb_resp = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert tb_resp.status_code == 200
    rows = {row["account_code"]: row for row in tb_resp.json()}
    assert rows["1100"]["total_debit"] == "1000.0000"
    assert rows["3100"]["total_credit"] == "1000.0000"


async def test_reversal_nets_trial_balance_to_zero(client):
    _, headers = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")

    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-02-01",
            "lines": [
                {"account_id": cash_id, "debit": 2000, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 2000},
            ],
        },
    )
    entry_id = create_resp.json()["id"]
    await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)

    reverse_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:reverse", headers=headers)
    assert reverse_resp.status_code == 200
    assert reverse_resp.json()["status"] == "posted"
    assert reverse_resp.json()["id"] != entry_id

    tb_resp = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in tb_resp.json()}
    assert rows["1100"]["total_debit"] == rows["1100"]["total_credit"] == "2000.0000"


async def test_trial_balance_opening_period_closing_columns(client):
    """Bundle E — Trial Balance redesign: an entry posted BEFORE the report's
    date_from must appear as opening_balance, not period_debit/period_credit;
    an entry posted WITHIN the range must appear as period activity only;
    closing_balance must equal opening + period debit - period credit,
    signed debit-minus-credit (positive = net debit)."""
    _, headers = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")

    # Prior-period entry (before the report window) -> becomes opening balance.
    prior = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-01-10",
            "lines": [
                {"account_id": cash_id, "debit": 5000, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 5000},
            ],
        },
    )
    await client.post(f"/api/v1/accounting/journal-entries/{prior.json()['id']}:post", headers=headers)

    # In-period entry -> becomes period_debit/period_credit.
    in_period = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-02-15",
            "lines": [
                {"account_id": cash_id, "debit": 1500, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 1500},
            ],
        },
    )
    await client.post(f"/api/v1/accounting/journal-entries/{in_period.json()['id']}:post", headers=headers)

    tb_resp = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-02-01", "date_to": "2026-02-28"},
    )
    assert tb_resp.status_code == 200
    rows = {row["account_code"]: row for row in tb_resp.json()}

    cash_row = rows["1100"]
    assert cash_row["opening_balance"] == "5000.0000"
    assert cash_row["period_debit"] == "1500.0000"
    assert cash_row["period_credit"] == "0.0000"
    assert cash_row["closing_balance"] == "6500.0000"

    capital_row = rows["3100"]
    # Credit-normal account: opening/closing are still reported debit-minus-credit
    # (negative = net credit), matching the universal trial-balance sign convention.
    assert capital_row["opening_balance"] == "-5000.0000"
    assert capital_row["period_credit"] == "1500.0000"
    assert capital_row["closing_balance"] == "-6500.0000"

    # Self-balancing invariant: every posted entry is debit=credit, so the
    # signed closing balance across ALL accounts must sum to zero.
    total_closing = sum(float(row["closing_balance"]) for row in rows.values())
    assert abs(total_closing) < 0.0001


async def test_trial_balance_abnormal_balance_reports_true_sign(client):
    """A liability account can legitimately end up with a net DEBIT balance
    (e.g. VAT Payable when input VAT exceeds output VAT in a period) —
    the backend must report the true signed closing_balance, not clamp or
    hide it. (The frontend separately flags this as an 'abnormal' balance
    for display, but must still show the real number.)"""
    _, headers = await _bootstrap_and_login(client)
    ap_id = await _get_account_id(client, headers, "2100")  # liability, credit-normal
    cash_id = await _get_account_id(client, headers, "1100")

    # Debit the liability account more than it's credited -> net debit balance.
    entry = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-03-05",
            "lines": [
                {"account_id": ap_id, "debit": 800, "credit": 0},
                {"account_id": cash_id, "debit": 0, "credit": 800},
            ],
        },
    )
    await client.post(f"/api/v1/accounting/journal-entries/{entry.json()['id']}:post", headers=headers)

    tb_resp = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-03-01", "date_to": "2026-03-31"},
    )
    rows = {row["account_code"]: row for row in tb_resp.json()}
    # Positive closing_balance = net debit, even though 2100 is a liability.
    assert rows["2100"]["closing_balance"] == "800.0000"


async def test_reversing_a_non_posted_entry_rejected(client):
    _, headers = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")

    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-03-01",
            "lines": [
                {"account_id": cash_id, "debit": 500, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 500},
            ],
        },
    )
    entry_id = create_resp.json()["id"]  # left in draft, never posted

    reverse_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:reverse", headers=headers)
    assert reverse_resp.status_code == 422


async def test_accounting_endpoints_require_permission(client):
    resp_no_auth = await client.get("/api/v1/accounting/chart-of-accounts")
    assert resp_no_auth.status_code == 401


async def test_create_account_with_unknown_type_code_rejected(client):
    _, headers = await _bootstrap_and_login(client)
    resp = await client.post(
        "/api/v1/accounting/chart-of-accounts",
        headers=headers,
        json={"code": "9999", "name": "Bogus", "account_type_code": "not-a-real-type"},
    )
    assert resp.status_code == 422


async def test_list_and_get_journal_entry(client):
    _, headers = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")

    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-04-01",
            "reference": "Opening capital",
            "lines": [
                {"account_id": cash_id, "debit": 750, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 750},
            ],
        },
    )
    entry_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/accounting/journal-entries", headers=headers)
    assert list_resp.status_code == 200
    assert any(e["id"] == entry_id for e in list_resp.json())

    detail_resp = await client.get(f"/api/v1/accounting/journal-entries/{entry_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["entry"]["id"] == entry_id
    assert detail["entry"]["reference"] == "Opening capital"
    lines_by_account = {line["account_id"]: line for line in detail["lines"]}
    assert lines_by_account[cash_id]["debit"] == "750.0000"
    assert lines_by_account[capital_id]["credit"] == "750.0000"


async def test_get_journal_entry_not_found(client):
    _, headers = await _bootstrap_and_login(client)
    resp = await client.get(
        "/api/v1/accounting/journal-entries/00000000-0000-0000-0000-000000000099", headers=headers
    )
    assert resp.status_code == 404


async def test_journal_entry_not_visible_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers_a, "1100")
    capital_id = await _get_account_id(client, headers_a, "3100")
    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers_a,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-04-02",
            "lines": [
                {"account_id": cash_id, "debit": 100, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 100},
            ],
        },
    )
    entry_id = create_resp.json()["id"]

    _, headers_b = await _bootstrap_and_login(client)
    resp = await client.get(f"/api/v1/accounting/journal-entries/{entry_id}", headers=headers_b)
    assert resp.status_code == 404


async def test_trial_balance_export_pdf_and_excel(client):
    """Standard Reporting Framework — every report endpoint must serve a
    real downloadable PDF/Excel via `format=pdf|xlsx`, not just JSON."""
    _, headers = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers, "1100")
    capital_id = await _get_account_id(client, headers, "3100")
    entry = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-02-15",
            "lines": [
                {"account_id": cash_id, "debit": 1500, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 1500},
            ],
        },
    )
    await client.post(f"/api/v1/accounting/journal-entries/{entry.json()['id']}:post", headers=headers)

    pdf_resp = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-02-01", "date_to": "2026-02-28", "format": "pdf", "lang": "ar"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert "trial-balance.pdf" in pdf_resp.headers["content-disposition"]
    assert pdf_resp.content[:4] == b"%PDF"

    xlsx_resp = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-02-01", "date_to": "2026-02-28", "format": "xlsx", "lang": "en"},
    )
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert xlsx_resp.content[:2] == b"PK"  # xlsx is a zip container


async def test_general_ledger_export_requires_permission(client):
    _, headers = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers, "1100")

    # No auth header at all -> export path must be permission-gated same as JSON.
    resp = await client.get(
        "/api/v1/accounting/reports/general-ledger",
        params={
            "account_id": cash_id,
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "format": "pdf",
        },
    )
    assert resp.status_code == 401


async def test_income_statement_and_balance_sheet_export(client):
    _, headers = await _bootstrap_and_login(client)
    cash_id = await _get_account_id(client, headers, "1100")
    revenue_id = await _get_account_id(client, headers, "4100")
    entry = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-03-01",
            "lines": [
                {"account_id": cash_id, "debit": 2000, "credit": 0},
                {"account_id": revenue_id, "debit": 0, "credit": 2000},
            ],
        },
    )
    await client.post(f"/api/v1/accounting/journal-entries/{entry.json()['id']}:post", headers=headers)

    is_resp = await client.get(
        "/api/v1/accounting/reports/income-statement",
        headers=headers,
        params={"date_from": "2026-03-01", "date_to": "2026-03-31", "format": "pdf"},
    )
    assert is_resp.status_code == 200
    assert is_resp.content[:4] == b"%PDF"

    bs_resp = await client.get(
        "/api/v1/accounting/reports/balance-sheet",
        headers=headers,
        params={"as_of_date": "2026-03-31", "format": "xlsx"},
    )
    assert bs_resp.status_code == 200
    assert bs_resp.content[:2] == b"PK"
