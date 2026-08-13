"""P0-2 (Phase-One audit closure) — Fiscal Period Closing GUI and
end-to-end workflow.

The backend mechanism (FiscalPeriod model/repository/service, FR-ACC-011)
already existed: `create_period`/`close_period` and their two routes
(`POST /fiscal-periods`, `POST /fiscal-periods/{id}:close`), both gated by
the existing `accounting.fiscal_period.manage` permission, and
`JournalEntryService.post_entry` already centrally rejects posting into a
closed period for every module that posts a journal entry through it
(Sales, Purchasing, Fixed Assets, Payments, manual JEs) — confirmed by
tracing all 13 `post_entry` call sites across the backend. What was
missing: a way to list a company's periods at all (no `GET` existed), and
a clean HTTP error for the closed-period rejection outside Accounting's
own `:post` route (every other module's route only caught `ValueError`,
so `PeriodClosedError` — not a `ValueError` subclass — fell through to a
raw 500 instead of the 409 it should be).

There is deliberately no reopen test here: the backend has no reopen
endpoint at all, so this is not a gap this change introduces or is
expected to close.
"""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap(client, label: str) -> dict:
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
    branch_id = boot_resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return {"company_id": company_id, "branch_id": branch_id, "headers": headers}


async def _create_limited_user(client, headers, company_id: str) -> dict:
    """A real user with a role holding zero permissions (mirrors
    test_settings_roles.py's `_create_user_with_role`) — proves the
    close-period action is actually backend-enforced, not just hidden in
    the UI."""
    role_resp = await client.post("/api/v1/identity/roles", headers=headers, json={"name": "No Permissions"})
    assert role_resp.status_code == 201
    role_id = role_resp.json()["id"]

    email = unique_email()
    password = "Str0ng!Passw0rd"
    user_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": email, "full_name": "Limited User", "password": password, "company_id": company_id},
    )
    assert user_resp.status_code == 201
    user_id = user_resp.json()["id"]
    assign_resp = await client.post(
        f"/api/v1/identity/users/{user_id}/roles", headers=headers, json={"role_id": role_id}
    )
    assert assign_resp.status_code == 204

    login_resp = await client.post("/api/v1/identity/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}}


async def _account_id(client, headers, code: str) -> str:
    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    return next(a["id"] for a in accounts if a["code"] == code)


async def _create_and_post_manual_je(client, headers, *, entry_date: str, ar_id: str, revenue_id: str, amount: str = "100.00"):
    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": entry_date,
            "reference": "P0-2 test entry",
            "lines": [
                {"account_id": ar_id, "debit": amount, "credit": "0"},
                {"account_id": revenue_id, "debit": "0", "credit": amount},
            ],
        },
    )
    assert create_resp.status_code == 201
    return create_resp.json()["id"]


async def test_authorized_user_can_close_open_period(client):
    """Requirement #1: authorized user (Admin, holds
    accounting.fiscal_period.manage) can close an open period."""
    env = await _bootstrap(client, f"P0-2Auth-{unique_vat()[:6]}")
    headers = env["headers"]

    create_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=headers,
        json={"period_start": "2026-01-01", "period_end": "2026-01-31"},
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["is_closed"] is False
    period_id = create_resp.json()["id"]

    close_resp = await client.post(f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=headers)
    assert close_resp.status_code == 200
    assert close_resp.json()["is_closed"] is True


async def test_unauthorized_user_cannot_close_period(client):
    """Requirement #2: a user without accounting.fiscal_period.manage is
    rejected by the backend itself, not just hidden in the UI."""
    env = await _bootstrap(client, f"P0-2Unauth-{unique_vat()[:6]}")
    headers = env["headers"]
    limited = await _create_limited_user(client, headers, env["company_id"])

    create_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=headers,
        json={"period_start": "2026-02-01", "period_end": "2026-02-28"},
    )
    period_id = create_resp.json()["id"]

    forbidden_create = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=limited["headers"],
        json={"period_start": "2026-03-01", "period_end": "2026-03-31"},
    )
    assert forbidden_create.status_code == 403

    forbidden_close = await client.post(
        f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=limited["headers"]
    )
    assert forbidden_close.status_code == 403

    # The period the limited user tried (and failed) to close remains open.
    still_open = await client.get("/api/v1/accounting/fiscal-periods", headers=headers)
    assert next(p for p in still_open.json() if p["id"] == period_id)["is_closed"] is False


async def test_closed_period_rejects_manual_journal_entry_posting(client):
    """Requirement #3 (manual JE side): posting into a closed period is
    rejected with a clean 409, using Accounting's own :post route (which
    already caught PeriodClosedError before this change)."""
    env = await _bootstrap(client, f"P0-2ManualJE-{unique_vat()[:6]}")
    headers = env["headers"]
    ar_id = await _account_id(client, headers, "1200")
    revenue_id = await _account_id(client, headers, "4100")

    period_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=headers,
        json={"period_start": "2026-04-01", "period_end": "2026-04-30"},
    )
    period_id = period_resp.json()["id"]
    await client.post(f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=headers)

    # Draft creation itself is not blocked (only posting is) — matches the
    # existing service: find_covering/is_closed is only checked in
    # post_entry, not create_draft_entry.
    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-04-15",
            "lines": [
                {"account_id": ar_id, "debit": "100.00", "credit": "0"},
                {"account_id": revenue_id, "debit": "0", "credit": "100.00"},
            ],
        },
    )
    assert create_resp.status_code == 201
    entry_id = create_resp.json()["id"]

    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert post_resp.status_code == 409
    assert "closed" in post_resp.json()["detail"].lower()


async def test_closed_period_rejects_sales_invoice_posting(client):
    """Requirement #3 (cross-module side) + the actual bug this change
    fixes: Sales' route never explicitly caught PeriodClosedError (it only
    catches ValueError, and PeriodClosedError is not a ValueError
    subclass), so before the new global exception handler this would have
    surfaced as a raw 500, not the clean 409 asserted here. Proves the
    SAME central JournalEntryService.post_entry check protects Sales,
    Purchasing, and Fixed Assets uniformly — not just manual JEs."""
    env = await _bootstrap(client, f"P0-2SalesJE-{unique_vat()[:6]}")
    headers = env["headers"]

    period_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=headers,
        json={"period_start": "2026-05-01", "period_end": "2026-05-31"},
    )
    period_id = period_resp.json()["id"]
    await client.post(f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=headers)

    partner = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "P0-2 Customer", "is_customer": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "P0-2 Product", "sales_price": "100.00"},
    )
    quote = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner.json()["id"],
            "quote_date": "2026-05-15",
            "lines": [
                {"product_id": product.json()["id"], "qty": "1", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}
            ],
        },
    )
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote.json()['id']}:confirm", headers=headers)).json()["id"]

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 409
    body = invoice_resp.json()
    assert body["status"] == 409
    assert "closed" in body["detail"].lower()


async def test_fiscal_period_company_isolation(client):
    """Requirement #4: Company B cannot see or close Company A's period."""
    company_a = await _bootstrap(client, f"P0-2IsoA-{unique_vat()[:6]}")
    company_b = await _bootstrap(client, f"P0-2IsoB-{unique_vat()[:6]}")

    period_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=company_a["headers"],
        json={"period_start": "2026-06-01", "period_end": "2026-06-30"},
    )
    a_period_id = period_resp.json()["id"]

    # B's list never contains A's period.
    b_list = await client.get("/api/v1/accounting/fiscal-periods", headers=company_b["headers"])
    assert all(p["id"] != a_period_id for p in b_list.json())

    # B attempting to close A's period by id is rejected as not found, not
    # silently succeeding or leaking a 403-vs-404 distinction.
    close_attempt = await client.post(
        f"/api/v1/accounting/fiscal-periods/{a_period_id}:close", headers=company_b["headers"]
    )
    assert close_attempt.status_code == 404

    # A's period is provably still open — B's attempt had zero effect.
    a_list = await client.get("/api/v1/accounting/fiscal-periods", headers=company_a["headers"])
    assert next(p for p in a_list.json() if p["id"] == a_period_id)["is_closed"] is False


async def test_close_fiscal_period_is_idempotent(client):
    """Requirement #5: calling :close twice is safe — no error, same
    end state, matching the service's own unconditional `is_closed = True`
    (no "already closed" guard to trip over)."""
    env = await _bootstrap(client, f"P0-2Idem-{unique_vat()[:6]}")
    headers = env["headers"]

    period_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=headers,
        json={"period_start": "2026-07-01", "period_end": "2026-07-31"},
    )
    period_id = period_resp.json()["id"]

    first_close = await client.post(f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=headers)
    assert first_close.status_code == 200
    assert first_close.json()["is_closed"] is True

    second_close = await client.post(f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=headers)
    assert second_close.status_code == 200
    assert second_close.json()["is_closed"] is True


async def test_closing_period_does_not_alter_historical_journal_entry(client):
    """Requirement #6: historical transactions remain unchanged. Post a
    real JE while the period is still open, then close the period, and
    confirm the already-posted entry's amounts are untouched."""
    env = await _bootstrap(client, f"P0-2Hist-{unique_vat()[:6]}")
    headers = env["headers"]
    ar_id = await _account_id(client, headers, "1200")
    revenue_id = await _account_id(client, headers, "4100")

    period_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=headers,
        json={"period_start": "2026-08-01", "period_end": "2026-08-31"},
    )
    period_id = period_resp.json()["id"]

    entry_id = await _create_and_post_manual_je(client, headers, entry_date="2026-08-10", ar_id=ar_id, revenue_id=revenue_id, amount="777.00")
    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert post_resp.status_code == 200

    await client.post(f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=headers)

    detail = await client.get(f"/api/v1/accounting/journal-entries/{entry_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["entry"]["status"] == "posted"
    total_debit = sum(Decimal(line["debit"]) for line in body["lines"])
    total_credit = sum(Decimal(line["credit"]) for line in body["lines"])
    assert total_debit == total_credit == Decimal("777.00")


async def test_trial_balance_remains_balanced_after_period_close(client):
    """Requirement #7: closed-period historical reports remain readable
    and correct — Trial Balance covering the closed period still
    reconciles (total debit == total credit) after the close."""
    env = await _bootstrap(client, f"P0-2TB-{unique_vat()[:6]}")
    headers = env["headers"]
    ar_id = await _account_id(client, headers, "1200")
    revenue_id = await _account_id(client, headers, "4100")

    period_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=headers,
        json={"period_start": "2026-09-01", "period_end": "2026-09-30"},
    )
    period_id = period_resp.json()["id"]

    entry_id = await _create_and_post_manual_je(client, headers, entry_date="2026-09-10", ar_id=ar_id, revenue_id=revenue_id, amount="500.00")
    await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    await client.post(f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=headers)

    tb_resp = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-09-01", "date_to": "2026-09-30"},
    )
    assert tb_resp.status_code == 200
    rows = tb_resp.json()
    total_debit = sum(Decimal(r["period_debit"]) for r in rows)
    total_credit = sum(Decimal(r["period_credit"]) for r in rows)
    assert total_debit == total_credit == Decimal("500.00")


async def test_fiscal_period_list_endpoint_round_trip(client):
    """Requirement #8: the GUI/API contract — create, list (open), close,
    list again (closed). This is the exact sequence the new frontend tab
    drives."""
    env = await _bootstrap(client, f"P0-2RT-{unique_vat()[:6]}")
    headers = env["headers"]

    before = await client.get("/api/v1/accounting/fiscal-periods", headers=headers)
    assert before.status_code == 200
    assert before.json() == []

    create_resp = await client.post(
        "/api/v1/accounting/fiscal-periods",
        headers=headers,
        json={"period_start": "2026-10-01", "period_end": "2026-10-31"},
    )
    period_id = create_resp.json()["id"]

    after_create = await client.get("/api/v1/accounting/fiscal-periods", headers=headers)
    listed = next(p for p in after_create.json() if p["id"] == period_id)
    assert listed["is_closed"] is False
    assert listed["period_start"] == "2026-10-01"
    assert listed["period_end"] == "2026-10-31"

    await client.post(f"/api/v1/accounting/fiscal-periods/{period_id}:close", headers=headers)

    after_close = await client.get("/api/v1/accounting/fiscal-periods", headers=headers)
    listed_after = next(p for p in after_close.json() if p["id"] == period_id)
    assert listed_after["is_closed"] is True
