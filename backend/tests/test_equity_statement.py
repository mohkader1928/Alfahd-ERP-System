"""Standard SME ERP — Accounting Financial Statements Phase C: Statement of
Changes in Equity. docs/23-cash-flow-equity-phase-a.md documents the
Owner-approved design and decisions this implements.

Every figure asserted here is derived from real posted Journal Entries
through the normal API, mirroring test_accounting_reports_m1a_smoke.py's
and test_cash_flow_statement.py's own convention.
"""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="EQ"):
    payload = {
        "tenant_legal_name": f"{label} Test Holding",
        "company_legal_name": f"{label} Test Trading Co.",
        "company_legal_name_ar": f"{label} Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": f"{label} Test Admin",
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
    """Same proven scenario as test_accounting_reports_m1a_smoke.py /
    test_cash_flow_statement.py: net_income=300, equity_total=5300 as of
    2026-05-31 (capital 5000 + current earnings 300)."""
    cash = await _get_account_id(client, headers, "1100")
    ar = await _get_account_id(client, headers, "1200")
    inventory = await _get_account_id(client, headers, "1300")
    vat_payable = await _get_account_id(client, headers, "2200")
    capital = await _get_account_id(client, headers, "3100")
    revenue = await _get_account_id(client, headers, "4100")
    cogs = await _get_account_id(client, headers, "5100")
    opex = await _get_account_id(client, headers, "5200")

    await _post_je(client, headers, "2026-05-01", [
        {"account_id": inventory, "debit": 1000, "credit": 0},
        {"account_id": cash, "debit": 0, "credit": 1000},
    ])
    await _post_je(client, headers, "2026-05-02", [
        {"account_id": cash, "debit": 5000, "credit": 0},
        {"account_id": capital, "debit": 0, "credit": 5000},
    ])
    await _post_je(client, headers, "2026-05-10", [
        {"account_id": ar, "debit": 1150, "credit": 0},
        {"account_id": revenue, "debit": 0, "credit": 1000},
        {"account_id": vat_payable, "debit": 0, "credit": 150},
    ])
    await _post_je(client, headers, "2026-05-10", [
        {"account_id": cogs, "debit": 600, "credit": 0},
        {"account_id": inventory, "debit": 0, "credit": 600},
    ])
    await _post_je(client, headers, "2026-05-15", [
        {"account_id": opex, "debit": 100, "credit": 0},
        {"account_id": cash, "debit": 0, "credit": 100},
    ])


async def _get_equity_statement(client, headers, date_from: str, date_to: str) -> dict:
    resp = await client.get(
        "/api/v1/accounting/reports/equity-statement",
        headers=headers,
        params={"date_from": date_from, "date_to": date_to},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# 1 (opening), 2 (profit/loss effect), 3 (capital contribution), 5 (closing)
async def test_equity_opening_profit_contribution_and_closing(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)

    body = await _get_equity_statement(client, headers, "2026-05-01", "2026-05-31")

    assert body["opening_equity"] == "0.0000"
    assert body["profit_for_period"] == "300.0000"  # matches income_statement's own net_income exactly
    assert body["contributions"] == "5000.0000"
    assert body["withdrawals"] == "0.0000"
    assert body["other_equity_lines"] == []
    assert body["other_equity_total"] == "0.0000"
    assert body["closing_equity"] == "5300.0000"  # 0 + 300 + 5000 - 0 + 0
    assert body["reconciliation_difference"] == "0.0000"
    assert set(body["unsupported_items"]) == {"dividends", "oci", "treasury_shares"}


# 4 (withdrawals)
async def test_equity_withdrawal_reduces_closing_equity(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)
    cash = await _get_account_id(client, headers, "1100")
    capital = await _get_account_id(client, headers, "3100")

    await _post_je(client, headers, "2026-05-20", [  # owner draws cash out
        {"account_id": capital, "debit": 800, "credit": 0},
        {"account_id": cash, "debit": 0, "credit": 800},
    ])

    body = await _get_equity_statement(client, headers, "2026-05-01", "2026-05-31")
    assert body["contributions"] == "5000.0000"
    assert body["withdrawals"] == "800.0000"
    assert body["closing_equity"] == "4500.0000"  # 0 + 300 + 5000 - 800 + 0
    assert body["reconciliation_difference"] == "0.0000"


async def test_equity_other_movements_surfaced_not_dropped(client):
    """A manual posting to an equity account OTHER than Owner's Capital
    (3100) -- e.g. Retained Earnings, 3200 -- must not be silently dropped
    or miscounted as a contribution/withdrawal; it shows as its own line
    and the statement still reconciles exactly."""
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)
    cash = await _get_account_id(client, headers, "1100")
    retained_earnings = await _get_account_id(client, headers, "3200")

    await _post_je(client, headers, "2026-05-25", [
        {"account_id": cash, "debit": 250, "credit": 0},
        {"account_id": retained_earnings, "debit": 0, "credit": 250},
    ])

    body = await _get_equity_statement(client, headers, "2026-05-01", "2026-05-31")
    assert body["contributions"] == "5000.0000"  # unaffected -- this wasn't a 3100 posting
    assert body["withdrawals"] == "0.0000"
    other_codes = {row["account_code"] for row in body["other_equity_lines"]}
    assert other_codes == {"3200"}
    assert body["other_equity_total"] == "250.0000"
    assert body["closing_equity"] == "5550.0000"  # 0 + 300 + 5000 - 0 + 250
    assert body["reconciliation_difference"] == "0.0000"


async def test_equity_multiple_periods_use_correct_opening_balance(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)
    cash = await _get_account_id(client, headers, "1100")
    revenue = await _get_account_id(client, headers, "4100")
    await _post_je(client, headers, "2026-06-10", [
        {"account_id": cash, "debit": 400, "credit": 0},
        {"account_id": revenue, "debit": 0, "credit": 400},
    ])

    period1 = await _get_equity_statement(client, headers, "2026-05-01", "2026-05-31")
    period2 = await _get_equity_statement(client, headers, "2026-06-01", "2026-06-30")

    assert period1["closing_equity"] == period2["opening_equity"]
    assert period2["profit_for_period"] == "400.0000"
    assert period2["closing_equity"] == "5700.0000"
    assert period2["reconciliation_difference"] == "0.0000"


async def test_equity_empty_period_returns_zeroes(client):
    _, headers = await _bootstrap_and_login(client)
    body = await _get_equity_statement(client, headers, "2026-01-01", "2026-12-31")

    assert body["opening_equity"] == "0.0000"
    assert body["profit_for_period"] == "0.0000"
    assert body["contributions"] == "0.0000"
    assert body["withdrawals"] == "0.0000"
    assert body["other_equity_lines"] == []
    assert body["closing_equity"] == "0.0000"
    assert body["reconciliation_difference"] == "0.0000"


# Cross-statement: Closing Equity must match Balance Sheet's own equity_total.
async def test_equity_closing_matches_balance_sheet(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)
    cash = await _get_account_id(client, headers, "1100")
    capital = await _get_account_id(client, headers, "3100")
    await _post_je(client, headers, "2026-05-20", [
        {"account_id": capital, "debit": 800, "credit": 0},
        {"account_id": cash, "debit": 0, "credit": 800},
    ])

    equity_statement = await _get_equity_statement(client, headers, "2026-05-01", "2026-05-31")
    bs_resp = await client.get(
        "/api/v1/accounting/reports/balance-sheet", headers=headers, params={"as_of_date": "2026-05-31"}
    )
    assert bs_resp.status_code == 200
    balance_sheet = bs_resp.json()

    assert Decimal(equity_statement["closing_equity"]) == Decimal(balance_sheet["equity_total"])


async def test_equity_isolated_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client, label="EQA")
    await _seed_business_core_activity(client, headers_a)

    _, headers_b = await _bootstrap_and_login(client, label="EQB")

    body_b = await _get_equity_statement(client, headers_b, "2026-01-01", "2026-12-31")
    assert body_b["profit_for_period"] == "0.0000"
    assert body_b["closing_equity"] == "0.0000"


async def test_equity_requires_authentication(client):
    resp = await client.get(
        "/api/v1/accounting/reports/equity-statement",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 401


async def test_equity_read_only_and_idempotent(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)

    first = await _get_equity_statement(client, headers, "2026-05-01", "2026-05-31")
    second = await _get_equity_statement(client, headers, "2026-05-01", "2026-05-31")
    assert first == second
