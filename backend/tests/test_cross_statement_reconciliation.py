"""Standard SME ERP — Accounting Financial Statements Phase, Phase D:
cross-statement reconciliation.

Every prior phase (M1a Income Statement/Balance Sheet, Phase B Cash Flow,
Phase C Statement of Changes in Equity) already proved its own numbers
against Balance Sheet in isolation. This file is the final proof the
Owner's brief asked for explicitly: ONE real company, ONE set of real
posted transactions, and all SIX reports (Trial Balance, General Ledger,
Income Statement, Balance Sheet, Cash Flow Statement, Statement of Changes
in Equity) read simultaneously and cross-checked against each other --
including the one relationship no single-report test exercises on its
own: that Income Statement's net_income, Balance Sheet's current_earnings,
Cash Flow's net_income, and Equity Statement's profit_for_period are the
exact same number, from four independently-called endpoints, not just
internally reused by one service method calling another.
"""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="XSTMT"):
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


async def _fetch_all_reports(client, headers, cash_account_id: str) -> dict:
    date_from, date_to = "2026-08-01", "2026-08-31"

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": date_from, "date_to": date_to},
    )
    general_ledger = await client.get(
        "/api/v1/accounting/reports/general-ledger",
        headers=headers,
        params={"account_id": cash_account_id, "date_from": date_from, "date_to": date_to},
    )
    income_statement = await client.get(
        "/api/v1/accounting/reports/income-statement",
        headers=headers,
        params={"date_from": date_from, "date_to": date_to},
    )
    balance_sheet = await client.get(
        "/api/v1/accounting/reports/balance-sheet", headers=headers, params={"as_of_date": date_to}
    )
    cash_flow = await client.get(
        "/api/v1/accounting/reports/cash-flow",
        headers=headers,
        params={"date_from": date_from, "date_to": date_to},
    )
    equity_statement = await client.get(
        "/api/v1/accounting/reports/equity-statement",
        headers=headers,
        params={"date_from": date_from, "date_to": date_to},
    )
    for resp in (trial_balance, general_ledger, income_statement, balance_sheet, cash_flow, equity_statement):
        assert resp.status_code == 200, resp.text

    return {
        "trial_balance": trial_balance.json(),
        "general_ledger": general_ledger.json(),
        "income_statement": income_statement.json(),
        "balance_sheet": balance_sheet.json(),
        "cash_flow": cash_flow.json(),
        "equity_statement": equity_statement.json(),
    }


async def test_all_six_statements_reconcile_for_one_real_scenario(client):
    """One company, nine real posted transactions spanning capital,
    a fixed-asset purchase, a credit sale with VAT, its COGS, a cash
    expense, depreciation, an owner withdrawal, and a manual posting to a
    non-capital equity account (Retained Earnings) -- deliberately
    combining, in a single scenario, every case each phase tested in
    isolation."""
    _, headers = await _bootstrap_and_login(client)
    cash = await _get_account_id(client, headers, "1100")
    ppe = await _get_account_id(client, headers, "1410")
    accum_dep = await _get_account_id(client, headers, "1490")
    inventory = await _get_account_id(client, headers, "1300")
    ar = await _get_account_id(client, headers, "1200")
    vat_payable = await _get_account_id(client, headers, "2200")
    capital = await _get_account_id(client, headers, "3100")
    retained_earnings = await _get_account_id(client, headers, "3200")
    revenue = await _get_account_id(client, headers, "4100")
    cogs = await _get_account_id(client, headers, "5100")
    opex = await _get_account_id(client, headers, "5200")
    dep_expense = await _get_account_id(client, headers, "5950")

    await _post_je(client, headers, "2026-08-01", [  # capital injection
        {"account_id": cash, "debit": 20000, "credit": 0},
        {"account_id": capital, "debit": 0, "credit": 20000},
    ])
    await _post_je(client, headers, "2026-08-03", [  # buy equipment for cash -> Investing
        {"account_id": ppe, "debit": 8000, "credit": 0},
        {"account_id": cash, "debit": 0, "credit": 8000},
    ])
    await _post_je(client, headers, "2026-08-05", [  # buy inventory for cash
        {"account_id": inventory, "debit": 3000, "credit": 0},
        {"account_id": cash, "debit": 0, "credit": 3000},
    ])
    await _post_je(client, headers, "2026-08-10", [  # credit sale with VAT
        {"account_id": ar, "debit": 4600, "credit": 0},
        {"account_id": revenue, "debit": 0, "credit": 4000},
        {"account_id": vat_payable, "debit": 0, "credit": 600},
    ])
    await _post_je(client, headers, "2026-08-10", [  # COGS for that sale
        {"account_id": cogs, "debit": 1800, "credit": 0},
        {"account_id": inventory, "debit": 0, "credit": 1800},
    ])
    await _post_je(client, headers, "2026-08-15", [  # cash operating expense
        {"account_id": opex, "debit": 500, "credit": 0},
        {"account_id": cash, "debit": 0, "credit": 500},
    ])
    await _post_je(client, headers, "2026-08-20", [  # depreciation -- no cash leg at all
        {"account_id": dep_expense, "debit": 200, "credit": 0},
        {"account_id": accum_dep, "debit": 0, "credit": 200},
    ])
    await _post_je(client, headers, "2026-08-25", [  # owner draws cash out
        {"account_id": capital, "debit": 1000, "credit": 0},
        {"account_id": cash, "debit": 0, "credit": 1000},
    ])
    await _post_je(client, headers, "2026-08-28", [  # manual posting to a NON-capital equity account
        {"account_id": cash, "debit": 300, "credit": 0},
        {"account_id": retained_earnings, "debit": 0, "credit": 300},
    ])

    reports = await _fetch_all_reports(client, headers, cash)

    # --- Fundamental double-entry identity: every posted period debit
    # equals every posted period credit, across the WHOLE trial balance. ---
    tb_rows = reports["trial_balance"]
    total_period_debit = sum(Decimal(r["period_debit"]) for r in tb_rows)
    total_period_credit = sum(Decimal(r["period_credit"]) for r in tb_rows)
    assert total_period_debit == total_period_credit

    # --- General Ledger for Cash matches the hand-derived balance. ---
    assert reports["general_ledger"]["closing_balance"] == "7800.0000"

    # --- Income Statement: Revenue 4000, COGS 1800, OpEx 700 (500 cash +
    # 200 depreciation), Net Income 1500. ---
    income = reports["income_statement"]
    assert income["revenue_total"] == "4000.0000"
    assert income["cogs_total"] == "1800.0000"
    assert income["opex_total"] == "700.0000"
    assert income["net_income"] == "1500.0000"

    # --- Balance Sheet: the one non-negotiable identity. ---
    balance_sheet = reports["balance_sheet"]
    assets_total = Decimal(balance_sheet["assets_total"])
    liabilities_total = Decimal(balance_sheet["liabilities_total"])
    equity_total = Decimal(balance_sheet["equity_total"])
    assert assets_total == liabilities_total + equity_total
    assert balance_sheet["current_earnings"] == "1500.0000"
    assert assets_total == Decimal("21400.0000")  # 7800 cash + 4600 AR + 1200 inventory + 8000 PP&E - 200 AccumDep
    assert liabilities_total == Decimal("600.0000")  # VAT Payable
    assert equity_total == Decimal("20800.0000")  # 19000 capital (net of withdrawal) + 300 RE + 1500 current earnings

    # --- Cash Flow: closing cash matches Balance Sheet's cash line exactly. ---
    cash_flow = reports["cash_flow"]
    cash_row = next(r for r in balance_sheet["assets"] if r["account_code"] == "1100")
    assert Decimal(cash_flow["closing_cash"]) == Decimal(cash_row["amount"])
    assert cash_flow["closing_cash"] == "7800.0000"
    assert cash_flow["investing_total"] == "-8000.0000"
    assert cash_flow["financing_total"] == "19300.0000"  # 20000 contribution - 1000 withdrawal + 300 (cash-touching equity posting)
    assert cash_flow["reconciliation_difference"] == "0.0000"

    # --- Equity Statement: closing equity matches Balance Sheet's equity_total exactly. ---
    equity_statement = reports["equity_statement"]
    assert Decimal(equity_statement["closing_equity"]) == equity_total
    assert equity_statement["closing_equity"] == "20800.0000"
    assert equity_statement["contributions"] == "20000.0000"
    assert equity_statement["withdrawals"] == "1000.0000"
    other_codes = {row["account_code"] for row in equity_statement["other_equity_lines"]}
    assert other_codes == {"3200"}
    assert equity_statement["reconciliation_difference"] == "0.0000"

    # --- The core cross-statement proof: Net Income is the EXACT SAME
    # number across all four endpoints that surface it, each queried
    # independently -- not merely internally reused within one call. ---
    assert (
        income["net_income"]
        == balance_sheet["current_earnings"]
        == cash_flow["net_income"]
        == equity_statement["profit_for_period"]
        == "1500.0000"
    )

    # --- Re-fetch everything: viewing reports must never mutate business
    # data, across all six reports simultaneously, not just individually. ---
    reports_again = await _fetch_all_reports(client, headers, cash)
    assert reports_again == reports
