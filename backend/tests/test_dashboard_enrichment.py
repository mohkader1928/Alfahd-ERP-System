"""Integration smoke test for Dashboard Enrichment (Product Owner audit:
the dashboard was 4 static KPI cards — the single most visible gap
against SAP B1/Dynamics 365 BC/Odoo/ERPNext, every one of which opens on
a trend chart, an actionable exceptions list, and a recent-activity feed).

Exercises: the sales trend spans the requested period_start/period_end
range (P0-8: previously a fixed 6-month trailing window, now one point
per calendar month within the caller's filter) and includes the current
month with the right total; pending_approvals_count reflects a real PO
stuck above the company's approval threshold; recent_activity surfaces
both a sales invoice and a purchase order, most recent first.
"""

from datetime import date
from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Dashboard Test Holding",
        "company_legal_name": "Dashboard Test Trading Co.",
        "company_legal_name_ar": "Dashboard Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Dashboard Test Admin",
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
    return company_id, headers


async def _issue_invoice(client, headers):
    partner = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Dash Customer", "is_customer": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"DASH-{unique_vat()[:8]}", "name": "Dash Product", "sales_price": "400.00"},
    )
    quote = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner.json()["id"],
            "quote_date": date.today().isoformat(),
            "lines": [{"product_id": product.json()["id"], "qty": "1", "unit_price": "400.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    return invoice_resp.json()["invoice"]


async def _set_threshold(client, headers, company_id, threshold: str):
    company = (await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)).json()
    resp = await client.patch(
        f"/api/v1/identity/companies/{company_id}",
        headers=headers,
        json={
            "legal_name": company["legal_name"],
            "legal_name_ar": company["legal_name_ar"],
            "vat_number": company["vat_number"],
            "cr_number": company["cr_number"],
            "po_approval_threshold": threshold,
        },
    )
    assert resp.status_code == 200


async def _create_and_confirm_po(client, headers, *, unit_price: str):
    vendor = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Dash Vendor", "is_vendor": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"DASHPO-{unique_vat()[:8]}", "name": "Dash Buy Product", "cost_price": unit_price},
    )
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor.json()["id"],
            "order_date": date.today().isoformat(),
            "lines": [{"product_id": product.json()["id"], "qty": "1", "unit_price": unit_price, "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    confirm_resp = await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    assert confirm_resp.status_code == 200
    return confirm_resp.json()


async def test_dashboard_reports_sales_trend_pending_approvals_and_recent_activity(client):
    company_id, headers = await _bootstrap_and_login(client)
    await _set_threshold(client, headers, company_id, "1000.0000")

    invoice = await _issue_invoice(client, headers)
    pending_po = await _create_and_confirm_po(client, headers, unit_price="5000.00")
    assert pending_po["status"] == "pending_approval"

    today = date.today()
    resp = await client.get(
        "/api/v1/reporting/dashboard",
        headers=headers,
        params={"period_start": f"{today.year}-01-01", "period_end": f"{today.year}-12-31"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Sales trend: P0-8 — one point per calendar month in the *requested*
    # range (here, the full Jan-Dec calendar year), not a fixed trailing
    # window disconnected from the period filter. Current month included
    # with a real total; December is last since the requested range ends
    # at year-end regardless of which month "today" falls in.
    assert len(body["sales_trend"]) == 12
    current_label = f"{today.year:04d}-{today.month:02d}"
    current_point = next(p for p in body["sales_trend"] if p["period_label"] == current_label)
    assert Decimal(current_point["total"]) >= Decimal("400.00")
    assert body["sales_trend"][-1]["period_label"] == f"{today.year:04d}-12"

    # Pending approvals: the one PO stuck above the threshold, not zero.
    assert body["pending_approvals_count"] == 1

    # Recent activity: both the invoice and the PO show up, correctly typed.
    activity_types = {(a["entity_type"], a["entity_id"]) for a in body["recent_activity"]}
    assert ("sales_invoice", invoice["id"]) in activity_types
    assert ("purchase_order", pending_po["id"]) in activity_types


async def test_dashboard_cash_balance_includes_split_bank_subaccounts(client):
    """Hardening Sub-stage 1, Issue #1A (Owner: "رصيد النقدية... اعتقد انه
    غير صحيح" while testing the dashboard). Root cause: the dashboard used
    to read the balance of account code "1100" (Cash and Bank) via an
    EXACT code match. The moment a company creates a second real account
    under "1100" (a completely normal action, e.g. a second bank account),
    ChartOfAccountsService auto-promotes "1100" to a non-postable group
    account -- so every posting from then on lands on the new child code,
    and an exact-code lookup silently stops seeing it. This reproduces
    exactly that: post to "1100" directly first (proving the baseline
    still works), then create "1101" as a child and post there too --
    the dashboard's cash_balance must include BOTH, not just the first."""
    company_id, headers = await _bootstrap_and_login(client)

    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    cash_1100 = next(a for a in accounts if a["code"] == "1100")
    capital = next(a for a in accounts if a["code"] == "3100")

    # 1) Post 1,000 directly to 1100 -- the pre-split baseline.
    je1 = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": date.today().isoformat(),
            "lines": [
                {"account_id": cash_1100["id"], "debit": "1000", "credit": "0"},
                {"account_id": capital["id"], "debit": "0", "credit": "1000"},
            ],
        },
    )
    assert je1.status_code == 201, je1.text
    await client.post(f"/api/v1/accounting/journal-entries/{je1.json()['id']}:post", headers=headers)

    # 2) Split: create "1101 Second Bank Account" as a real child of 1100 --
    # this is what auto-promotes 1100 to a non-postable group account.
    child_resp = await client.post(
        "/api/v1/accounting/chart-of-accounts",
        headers=headers,
        json={
            "code": "1101",
            "name": "Second Bank Account",
            "account_type_code": "asset",
            "parent_id": cash_1100["id"],
        },
    )
    assert child_resp.status_code == 201, child_resp.text
    cash_1101 = child_resp.json()

    # 1100 is now a group account -- confirms the split actually happened
    # and posting to it directly is now rejected (the real-world mechanism
    # that causes the bug).
    reject_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": date.today().isoformat(),
            "lines": [
                {"account_id": cash_1100["id"], "debit": "1", "credit": "0"},
                {"account_id": capital["id"], "debit": "0", "credit": "1"},
            ],
        },
    )
    assert reject_resp.status_code == 422

    # 3) Post 500 to the new child 1101 -- everything real now happens here.
    je2 = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": date.today().isoformat(),
            "lines": [
                {"account_id": cash_1101["id"], "debit": "500", "credit": "0"},
                {"account_id": capital["id"], "debit": "0", "credit": "500"},
            ],
        },
    )
    assert je2.status_code == 201, je2.text
    await client.post(f"/api/v1/accounting/journal-entries/{je2.json()['id']}:post", headers=headers)

    today = date.today()
    resp = await client.get(
        "/api/v1/reporting/dashboard",
        headers=headers,
        params={"period_start": f"{today.year}-01-01", "period_end": f"{today.year}-12-31"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The bug: cash_balance would report only 1000 (or even 0, depending on
    # timing) since it can no longer see anything posted to 1101. Correct:
    # 1000 (pre-split, still on 1100) + 500 (post-split, on 1101) = 1500.
    assert Decimal(body["cash_balance"]) == Decimal("1500.0000")


async def test_dashboard_with_no_activity_reports_zero_not_error(client):
    _, headers = await _bootstrap_and_login(client)
    today = date.today()
    resp = await client.get(
        "/api/v1/reporting/dashboard",
        headers=headers,
        params={"period_start": f"{today.year}-01-01", "period_end": f"{today.year}-12-31"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pending_approvals_count"] == 0
    assert body["recent_activity"] == []
    assert len(body["sales_trend"]) == 12
    assert all(Decimal(p["total"]) == 0 for p in body["sales_trend"])
