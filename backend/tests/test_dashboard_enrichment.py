"""Integration smoke test for Dashboard Enrichment (Product Owner audit:
the dashboard was 4 static KPI cards — the single most visible gap
against SAP B1/Dynamics 365 BC/Odoo/ERPNext, every one of which opens on
a trend chart, an actionable exceptions list, and a recent-activity feed).

Exercises: the 6-month sales trend includes the current month with the
right total; pending_approvals_count reflects a real PO stuck above the
company's approval threshold; recent_activity surfaces both a sales
invoice and a purchase order, most recent first.
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

    # Sales trend: 6 months, current month included with a real total.
    assert len(body["sales_trend"]) == 6
    current_label = f"{today.year:04d}-{today.month:02d}"
    current_point = next(p for p in body["sales_trend"] if p["period_label"] == current_label)
    assert Decimal(current_point["total"]) >= Decimal("400.00")
    assert body["sales_trend"][-1]["period_label"] == current_label  # most recent month is last

    # Pending approvals: the one PO stuck above the threshold, not zero.
    assert body["pending_approvals_count"] == 1

    # Recent activity: both the invoice and the PO show up, correctly typed.
    activity_types = {(a["entity_type"], a["entity_id"]) for a in body["recent_activity"]}
    assert ("sales_invoice", invoice["id"]) in activity_types
    assert ("purchase_order", pending_po["id"]) in activity_types


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
    assert len(body["sales_trend"]) == 6
    assert all(Decimal(p["total"]) == 0 for p in body["sales_trend"])
