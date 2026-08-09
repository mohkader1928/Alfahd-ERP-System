"""Owner-requested follow-up to P0-4: a "detail level" selector for Trial
Balance / Income Statement / Balance Sheet, rolling deeper sub-accounts up
into their ancestor at the requested level instead of always listing
every leaf account. Builds on the account-hierarchy plumbing from
test_chart_of_accounts_hierarchy.py.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client, label="DetailLevel"):
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
    assert boot_resp.status_code == 201
    company_id = boot_resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return company_id, headers


async def _get_account(client, headers, code: str) -> dict:
    resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    return next(a for a in resp.json() if a["code"] == code)


async def test_trial_balance_rolls_up_subaccount_into_level_2_ancestor(client):
    _, headers = await _bootstrap_and_login(client, "TB_L2")
    cash = await _get_account(client, headers, "1100")
    petty = (
        await client.post(
            "/api/v1/accounting/chart-of-accounts",
            headers=headers,
            json={"code": "1110", "name": "Petty Cash", "account_type_code": "asset", "parent_id": cash["id"]},
        )
    ).json()
    capital = await _get_account(client, headers, "3100")

    await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-01",
            "lines": [
                {"account_id": petty["id"], "debit": "500.00", "credit": "0"},
                {"account_id": capital["id"], "debit": "0", "credit": "500.00"},
            ],
        },
    )
    posted = (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json()
    await client.post(f"/api/v1/accounting/journal-entries/{posted[0]['id']}:post", headers=headers)

    full = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    full_rows = {r["account_code"]: r for r in full.json()}
    assert "1110" in full_rows  # no rollup requested -> leaf account shows

    rolled = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31", "detail_level": 2},
    )
    rolled_rows = {r["account_code"]: r for r in rolled.json()}
    assert "1110" not in rolled_rows  # rolled into its level-2 parent
    assert rolled_rows["1100"]["period_debit"] == "500.0000"


async def test_trial_balance_rolls_up_to_level_1_top_category(client):
    _, headers = await _bootstrap_and_login(client, "TB_L1")
    ar = await _get_account(client, headers, "1200")
    inventory = await _get_account(client, headers, "1300")
    capital = await _get_account(client, headers, "3100")

    await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-01",
            "lines": [
                {"account_id": ar["id"], "debit": "100.00", "credit": "0"},
                {"account_id": inventory["id"], "debit": "200.00", "credit": "0"},
                {"account_id": capital["id"], "debit": "0", "credit": "300.00"},
            ],
        },
    )
    posted = (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json()
    entry_id = posted[0]["id"]
    await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)

    rolled = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31", "detail_level": 1},
    )
    rows = {r["account_code"]: r for r in rolled.json()}
    # Both 1200 (Accounts Receivable) and 1300 (Inventory) roll up into
    # 1000 (Assets); 3100 (Owner's Capital) rolls up into 3000 (Equity).
    assert "1200" not in rows and "1300" not in rows and "3100" not in rows
    assert rows["1000"]["period_debit"] == "300.0000"
    assert rows["3000"]["period_credit"] == "300.0000"


async def test_income_statement_rolls_up_revenue_and_expense_accounts(client):
    _, headers = await _bootstrap_and_login(client, "IS_Rollup")
    sales_revenue = await _get_account(client, headers, "4100")
    cogs = await _get_account(client, headers, "5100")
    opex = await _get_account(client, headers, "5200")
    cash = await _get_account(client, headers, "1100")

    await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-01",
            "lines": [
                {"account_id": cash["id"], "debit": "1000.00", "credit": "0"},
                {"account_id": sales_revenue["id"], "debit": "0", "credit": "1000.00"},
            ],
        },
    )
    await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-02",
            "lines": [
                {"account_id": cogs["id"], "debit": "300.00", "credit": "0"},
                {"account_id": opex["id"], "debit": "50.00", "credit": "0"},
                {"account_id": cash["id"], "debit": "0", "credit": "350.00"},
            ],
        },
    )
    for entry in (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json():
        await client.post(f"/api/v1/accounting/journal-entries/{entry['id']}:post", headers=headers)

    resp = await client.get(
        "/api/v1/accounting/reports/income-statement",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31", "detail_level": 1},
    )
    body = resp.json()
    # Revenue rolls up to 4000; totals are identical regardless of rollup
    # since they're independent sums, not derived from the row list.
    assert [r["account_code"] for r in body["revenue_accounts"]] == ["4000"]
    assert body["revenue_total"] == "1000.0000"
    assert body["cogs_total"] == "300.0000"
    assert body["opex_total"] == "50.0000"
    assert body["net_income"] == "650.0000"


async def test_balance_sheet_rolls_up_and_totals_stay_correct(client):
    _, headers = await _bootstrap_and_login(client, "BS_Rollup")
    cash = await _get_account(client, headers, "1100")
    ar = await _get_account(client, headers, "1200")
    capital = await _get_account(client, headers, "3100")

    await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-01",
            "lines": [
                {"account_id": cash["id"], "debit": "600.00", "credit": "0"},
                {"account_id": ar["id"], "debit": "400.00", "credit": "0"},
                {"account_id": capital["id"], "debit": "0", "credit": "1000.00"},
            ],
        },
    )
    entry_id = (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json()[0]["id"]
    await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)

    resp = await client.get(
        "/api/v1/accounting/reports/balance-sheet",
        headers=headers,
        params={"as_of_date": "2026-12-31", "detail_level": 1},
    )
    body = resp.json()
    assert [r["account_code"] for r in body["assets"]] == ["1000"]
    assert body["assets_total"] == "1000.0000"
    assert [r["account_code"] for r in body["equity"]] == ["3000"]
    # Fundamental identity must still hold after rollup.
    assert body["assets_total"] == body["total_liabilities_and_equity"]
