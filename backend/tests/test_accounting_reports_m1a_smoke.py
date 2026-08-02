"""Integration smoke test for Milestone 1a — Accounting Standardization
(General Ledger, Income Statement, Balance Sheet).

Every figure asserted here is derived from real posted Journal Entries
through the normal API — nothing is asserted against a hand-computed
"expected report row" without also posting the entries that produce it, so
these tests double as proof that Revenue -> COGS -> Gross Profit ->
Operating Expenses -> Net Income -> (unclosed) Current Earnings on the
Balance Sheet is a real, traceable chain, not a separate reporting table.
"""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Reports Test Holding",
        "company_legal_name": "Reports Test Trading Co.",
        "company_legal_name_ar": "Reports Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Reports Test Admin",
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


async def _seed_business_core_activity(client, headers):
    """Posts a small, internally-consistent business scenario: capital
    injection, a stock purchase, a sale (with VAT), the COGS for that sale,
    and an operating expense payment — the same shape of activity Sales +
    Purchasing + Payments already post automatically, reproduced directly
    via Journal Entries so this test doesn't depend on those modules."""
    cash = await _get_account_id(client, headers, "1100")
    ar = await _get_account_id(client, headers, "1200")
    inventory = await _get_account_id(client, headers, "1300")
    ap_or_vat = await _get_account_id(client, headers, "2200")
    capital = await _get_account_id(client, headers, "3100")
    revenue = await _get_account_id(client, headers, "4100")
    cogs = await _get_account_id(client, headers, "5100")
    opex = await _get_account_id(client, headers, "5200")

    await _post_je(  # JE0: buy inventory for cash
        client, headers, "2026-05-01", [
            {"account_id": inventory, "debit": 1000, "credit": 0},
            {"account_id": cash, "debit": 0, "credit": 1000},
        ],
    )
    await _post_je(  # JE1: owner capital injection
        client, headers, "2026-05-02", [
            {"account_id": cash, "debit": 5000, "credit": 0},
            {"account_id": capital, "debit": 0, "credit": 5000},
        ],
    )
    await _post_je(  # JE2: a sale on credit, with VAT
        client, headers, "2026-05-10", [
            {"account_id": ar, "debit": 1150, "credit": 0},
            {"account_id": revenue, "debit": 0, "credit": 1000},
            {"account_id": ap_or_vat, "debit": 0, "credit": 150},
        ],
    )
    await _post_je(  # JE3: COGS for that sale
        client, headers, "2026-05-10", [
            {"account_id": cogs, "debit": 600, "credit": 0},
            {"account_id": inventory, "debit": 0, "credit": 600},
        ],
    )
    await _post_je(  # JE4: an operating expense paid in cash
        client, headers, "2026-05-15", [
            {"account_id": opex, "debit": 100, "credit": 0},
            {"account_id": cash, "debit": 0, "credit": 100},
        ],
    )
    return {"cash": cash, "ar": ar, "inventory": inventory, "revenue": revenue, "cogs": cogs, "opex": opex}


async def test_general_ledger_opening_and_running_balance(client):
    _, headers = await _bootstrap_and_login(client)
    accounts = await _seed_business_core_activity(client, headers)

    # Everything before 2026-05-10 already hit Cash (JE0: -1000, JE1: +5000)
    # so the opening balance for a window starting on 2026-05-10 must be 4000.
    resp = await client.get(
        "/api/v1/accounting/reports/general-ledger",
        headers=headers,
        params={"account_id": accounts["cash"], "date_from": "2026-05-10", "date_to": "2026-05-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["opening_balance"] == "4000.0000"
    # Only JE4 (-100) falls inside this window.
    assert len(body["lines"]) == 1
    assert body["lines"][0]["credit"] == "100.0000"
    assert body["lines"][0]["running_balance"] == "3900.0000"
    assert body["closing_balance"] == "3900.0000"


async def test_general_ledger_unknown_account_404(client):
    _, headers = await _bootstrap_and_login(client)
    resp = await client.get(
        "/api/v1/accounting/reports/general-ledger",
        headers=headers,
        params={
            "account_id": "00000000-0000-0000-0000-000000000099",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        },
    )
    assert resp.status_code == 404


async def test_income_statement_computes_gross_and_net_correctly(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)

    resp = await client.get(
        "/api/v1/accounting/reports/income-statement",
        headers=headers,
        params={"date_from": "2026-05-01", "date_to": "2026-05-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["revenue_total"] == "1000.0000"
    assert body["cogs_total"] == "600.0000"
    assert body["gross_profit"] == "400.0000"
    assert body["opex_total"] == "100.0000"
    assert body["operating_income"] == "300.0000"
    assert body["net_income"] == "300.0000"
    # The COGS account must be bucketed separately from Operating Expenses,
    # not lumped into one "expense" total.
    cogs_codes = {row["account_code"] for row in body["cogs_accounts"]}
    opex_codes = {row["account_code"] for row in body["opex_accounts"]}
    assert cogs_codes == {"5100"}
    assert opex_codes == {"5200"}


async def test_balance_sheet_balances_assets_against_liabilities_plus_equity(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)

    resp = await client.get(
        "/api/v1/accounting/reports/balance-sheet", headers=headers, params={"as_of_date": "2026-05-31"}
    )
    assert resp.status_code == 200
    body = resp.json()

    assets_total = Decimal(body["assets_total"])
    liabilities_total = Decimal(body["liabilities_total"])
    equity_total = Decimal(body["equity_total"])
    current_earnings = Decimal(body["current_earnings"])

    # Cash 3900 (5000 - 1000 - 100) + AR 1150 + Inventory 400 (1000 - 600)
    assert assets_total == Decimal("5450.0000")
    # VAT Payable 150
    assert liabilities_total == Decimal("150.0000")
    # Capital 5000 + unclosed current earnings 300 (the net income proven above)
    assert current_earnings == Decimal("300.0000")
    assert equity_total == Decimal("5300.0000")
    # The one non-negotiable accounting identity this whole report exists to prove:
    assert assets_total == liabilities_total + equity_total
    assert Decimal(body["total_liabilities_and_equity"]) == assets_total


async def test_accounting_reports_isolated_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers_a)

    _, headers_b = await _bootstrap_and_login(client)  # a fresh, unrelated company

    resp = await client.get(
        "/api/v1/accounting/reports/income-statement",
        headers=headers_b,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["revenue_total"] == "0.0000"
    assert body["net_income"] == "0.0000"

    bs_resp = await client.get(
        "/api/v1/accounting/reports/balance-sheet", headers=headers_b, params={"as_of_date": "2026-12-31"}
    )
    bs_body = bs_resp.json()
    assert bs_body["assets_total"] == "0.0000"
    assert bs_body["assets_total"] == bs_body["total_liabilities_and_equity"]


async def test_accounting_reports_require_permission(client):
    resp = await client.get(
        "/api/v1/accounting/reports/income-statement",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 401
