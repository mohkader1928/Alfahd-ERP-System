"""Standard SME ERP — Accounting Financial Statements Phase B: Cash Flow
Statement (IAS 7, indirect method). docs/23-cash-flow-equity-phase-a.md
documents the Owner-approved design and decisions this implements.

Every figure asserted here is derived from real posted Journal Entries
through the normal API, mirroring test_accounting_reports_m1a_smoke.py's
own convention -- nothing is asserted against a hand-computed "expected
report row" without also posting the entries that produce it.
"""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="CF"):
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
    """Same scenario as test_accounting_reports_m1a_smoke.py's own helper —
    capital injection, an inventory purchase, a credit sale with VAT, its
    COGS, and a cash-paid operating expense — proven elsewhere to produce
    net_income=300 and closing Cash=3900 as of 2026-05-31."""
    cash = await _get_account_id(client, headers, "1100")
    ar = await _get_account_id(client, headers, "1200")
    inventory = await _get_account_id(client, headers, "1300")
    vat_payable = await _get_account_id(client, headers, "2200")
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
    await _post_je(  # JE2: a sale on credit, with VAT (no cash yet)
        client, headers, "2026-05-10", [
            {"account_id": ar, "debit": 1150, "credit": 0},
            {"account_id": revenue, "debit": 0, "credit": 1000},
            {"account_id": vat_payable, "debit": 0, "credit": 150},
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
    return {
        "cash": cash, "ar": ar, "inventory": inventory, "vat_payable": vat_payable,
        "capital": capital, "revenue": revenue, "cogs": cogs, "opex": opex,
    }


async def _get_cash_flow(client, headers, date_from: str, date_to: str) -> dict:
    resp = await client.get(
        "/api/v1/accounting/reports/cash-flow",
        headers=headers,
        params={"date_from": date_from, "date_to": date_to},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# 1-6: operating / investing / financing / opening / closing / net movement,
# all proven together since they're one computed report -- and cross-checked
# against Income Statement's independently-proven net_income=300 (test
# 17/19) and General Ledger's independently-proven closing Cash=3900.
async def test_cash_flow_operating_financing_and_reconciliation(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)

    body = await _get_cash_flow(client, headers, "2026-05-01", "2026-05-31")

    assert body["opening_cash"] == "0.0000"
    assert body["net_income"] == "300.0000"  # matches income_statement's own net_income exactly
    assert body["depreciation_addback"] == "0.0000"

    wc_by_code = {row["account_code"]: row["amount"] for row in body["working_capital_lines"]}
    assert wc_by_code["1300"] == "-400.0000"  # Inventory: -1000 (JE0) + 600 (JE3)
    assert wc_by_code["1200"] == "-1150.0000"  # AR: credit sale not yet collected
    assert wc_by_code["2200"] == "150.0000"  # VAT Payable: source of cash (not yet paid)
    assert body["working_capital_total"] == "-1400.0000"

    assert body["operating_total"] == "-1100.0000"  # 300 + 0 - 1400
    assert body["investing_total"] == "0.0000"
    assert body["financing_total"] == "5000.0000"  # owner capital injection
    financing_codes = {row["account_code"] for row in body["financing_lines"]}
    assert financing_codes == {"3100"}

    assert body["net_change_in_cash"] == "3900.0000"  # -1100 + 0 + 5000
    assert body["closing_cash"] == "3900.0000"  # matches General Ledger's independently-proven Cash balance
    assert body["reconciliation_difference"] == "0.0000"  # Opening + Net Change = Closing, exactly


# 2 (investing) + 8 (non-cash exclusion, depreciation specifically)
async def test_cash_flow_investing_and_depreciation_addback_excludes_noncash(client):
    _, headers = await _bootstrap_and_login(client)
    cash = await _get_account_id(client, headers, "1100")
    ppe = await _get_account_id(client, headers, "1410")
    accum_dep = await _get_account_id(client, headers, "1490")
    dep_expense = await _get_account_id(client, headers, "5950")
    capital = await _get_account_id(client, headers, "3100")

    await _post_je(client, headers, "2026-06-01", [  # fund the company first
        {"account_id": cash, "debit": 10000, "credit": 0},
        {"account_id": capital, "debit": 0, "credit": 10000},
    ])
    await _post_je(client, headers, "2026-06-05", [  # buy equipment for cash -> Investing
        {"account_id": ppe, "debit": 4000, "credit": 0},
        {"account_id": cash, "debit": 0, "credit": 4000},
    ])
    await _post_je(client, headers, "2026-06-30", [  # depreciation: NO cash leg at all
        {"account_id": dep_expense, "debit": 200, "credit": 0},
        {"account_id": accum_dep, "debit": 0, "credit": 200},
    ])

    body = await _get_cash_flow(client, headers, "2026-06-01", "2026-06-30")

    assert body["investing_total"] == "-4000.0000"
    investing_codes = {row["account_code"] for row in body["investing_lines"]}
    assert investing_codes == {"1410"}

    # The depreciation entry has no cash leg -- it must not appear as an
    # investing/financing movement, and must not inflate operating cash flow
    # either: it only shows up via the explicit add-back, which exactly
    # cancels the drag it puts on net_income.
    assert body["depreciation_addback"] == "200.0000"
    assert body["net_income"] == "-200.0000"  # depreciation is the only P&L activity this period
    assert body["operating_total"] == "0.0000"  # -200 net_income + 200 addback + 0 working capital
    assert body["reconciliation_difference"] == "0.0000"

    # True cash effect this period: +10000 (capital) - 4000 (equipment) = 6000
    assert body["net_change_in_cash"] == "6000.0000"
    assert body["closing_cash"] == "6000.0000"


async def test_cash_flow_non_cash_accrual_excluded(client):
    """A pure accrual (expense recognized, nothing paid) must not appear as
    a cash outflow anywhere in the statement -- it has no cash leg at all."""
    _, headers = await _bootstrap_and_login(client)
    opex = await _get_account_id(client, headers, "5200")
    accrued = await _get_account_id(client, headers, "2300")  # GRNI, reused as a generic accrual liability

    await _post_je(client, headers, "2026-07-15", [
        {"account_id": opex, "debit": 500, "credit": 0},
        {"account_id": accrued, "debit": 0, "credit": 500},
    ])

    body = await _get_cash_flow(client, headers, "2026-07-01", "2026-07-31")
    assert body["opening_cash"] == "0.0000"
    assert body["closing_cash"] == "0.0000"  # no cash ever moved
    assert body["net_change_in_cash"] == "0.0000"
    # net_income(-500) + WC(+500, the accrued liability increase) = 0 operating
    assert body["operating_total"] == "0.0000"
    assert body["reconciliation_difference"] == "0.0000"


async def test_cash_flow_multiple_periods_use_correct_opening_balance(client):
    """Period 2's Opening Cash must equal Period 1's Closing Cash — proven
    by running two consecutive, non-overlapping windows over the same
    activity rather than asserting a hardcoded number for period 2."""
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)
    # A second, later cash sale entirely within "period 2" below.
    cash = await _get_account_id(client, headers, "1100")
    revenue = await _get_account_id(client, headers, "4100")
    await _post_je(client, headers, "2026-06-10", [
        {"account_id": cash, "debit": 777, "credit": 0},
        {"account_id": revenue, "debit": 0, "credit": 777},
    ])

    period1 = await _get_cash_flow(client, headers, "2026-05-01", "2026-05-31")
    period2 = await _get_cash_flow(client, headers, "2026-06-01", "2026-06-30")

    assert period1["closing_cash"] == period2["opening_cash"]
    assert period2["net_income"] == "777.0000"
    assert period2["operating_total"] == "777.0000"
    assert period2["net_change_in_cash"] == "777.0000"
    assert period2["reconciliation_difference"] == "0.0000"


async def test_cash_flow_empty_period_returns_zeroes(client):
    _, headers = await _bootstrap_and_login(client)
    body = await _get_cash_flow(client, headers, "2026-01-01", "2026-12-31")

    assert body["opening_cash"] == "0.0000"
    assert body["net_income"] == "0.0000"
    assert body["depreciation_addback"] == "0.0000"
    assert body["working_capital_lines"] == []
    assert body["operating_total"] == "0.0000"
    assert body["investing_total"] == "0.0000"
    assert body["financing_total"] == "0.0000"
    assert body["net_change_in_cash"] == "0.0000"
    assert body["closing_cash"] == "0.0000"
    assert body["reconciliation_difference"] == "0.0000"


# 17 (cross-statement): Cash Flow's Closing Cash must equal the same
# is_cash_equivalent balance Balance Sheet would report for those accounts.
async def test_cash_flow_closing_cash_matches_balance_sheet(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)

    cash_flow = await _get_cash_flow(client, headers, "2026-05-01", "2026-05-31")
    bs_resp = await client.get(
        "/api/v1/accounting/reports/balance-sheet", headers=headers, params={"as_of_date": "2026-05-31"}
    )
    assert bs_resp.status_code == 200
    balance_sheet = bs_resp.json()
    cash_row = next(r for r in balance_sheet["assets"] if r["account_code"] == "1100")

    assert Decimal(cash_flow["closing_cash"]) == Decimal(cash_row["amount"])


# 20 (company isolation / RLS)
async def test_cash_flow_isolated_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client, label="CFA")
    await _seed_business_core_activity(client, headers_a)

    _, headers_b = await _bootstrap_and_login(client, label="CFB")  # a fresh, unrelated company

    body_b = await _get_cash_flow(client, headers_b, "2026-01-01", "2026-12-31")
    assert body_b["net_income"] == "0.0000"
    assert body_b["closing_cash"] == "0.0000"


# 21 (RBAC)
async def test_cash_flow_requires_authentication(client):
    resp = await client.get(
        "/api/v1/accounting/reports/cash-flow",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 401


# 23: reading the report must never mutate business data — same window
# fetched twice must return byte-identical figures.
async def test_cash_flow_read_only_and_idempotent(client):
    _, headers = await _bootstrap_and_login(client)
    await _seed_business_core_activity(client, headers)

    first = await _get_cash_flow(client, headers, "2026-05-01", "2026-05-31")
    second = await _get_cash_flow(client, headers, "2026-05-01", "2026-05-31")
    assert first == second
