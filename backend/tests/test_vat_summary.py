"""Integration smoke test for the VAT/Tax Summary report.

Explicitly named in the Owner's original Bundle E spec: output VAT
(sales) vs. input VAT (purchases) for a period, netted to what's owed.
Mirrors the bootstrap/invoice pattern in test_sales_reporting_bundle_e.py
and the procure-to-pay pattern in test_purchasing_m4_smoke.py.
"""

from datetime import date, timedelta
from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "VAT Test Holding",
        "company_legal_name": "VAT Test Trading Co.",
        "company_legal_name_ar": "VAT Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "VAT Test Admin",
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


async def _issue_sale(client, headers, *, invoice_date: str):
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "VAT Sale Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": "VAT-SALE-01", "name": "VAT Sale Product", "sales_price": "100.00"},
    )
    product_id = product_resp.json()["id"]
    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": invoice_date,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    return invoice_resp.json()["invoice"]


async def _create_vendor(client, headers):
    resp = await client.post("/api/v1/identity/partners", headers=headers, json={"name": "VAT Bill Vendor", "is_vendor": True})
    return resp.json()["id"]


async def _create_product(client, headers):
    resp = await client.post(
        "/api/v1/identity/products", headers=headers, json={"sku": "VAT-BUY-01", "name": "VAT Buy Product", "cost_price": "40.00"}
    )
    return resp.json()["id"]


async def _ensure_default_warehouse(client, headers):
    existing = await client.get("/api/v1/inventory/warehouses", headers=headers)
    if existing.status_code == 200 and existing.json():
        return
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "VAT Test Warehouse", "is_default": True})


async def _post_vendor_bill(client, headers, *, bill_date: str):
    await _ensure_default_warehouse(client, headers)
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": bill_date,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "40.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    gr_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "1"}]},
    )
    assert gr_resp.status_code == 201, gr_resp.text
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "VBILL-1", "lines": [{"purchase_order_line_id": po_line_id, "qty": "1", "unit_price": "40.00"}]},
    )
    assert bill_resp.json()["status"] == "matched", bill_resp.text
    bill_id = bill_resp.json()["id"]
    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)
    assert approve_resp.status_code == 200, approve_resp.text
    return approve_resp.json()


async def test_vat_summary_nets_output_and_input_vat(client):
    # Sales/purchase documents post with invoice_date/bill_date = date.today()
    # regardless of the quote_date/order_date supplied at draft time (invoices
    # are dated when actually issued, not when quoted) — so the report window
    # must bracket today, not an arbitrary past date.
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_sale(client, headers, invoice_date=today.isoformat())
    bill = await _post_vendor_bill(client, headers, bill_date=today.isoformat())

    resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert Decimal(body["sales_subtotal"]) == Decimal(invoice["subtotal_amount"])
    assert Decimal(body["output_vat"]) == Decimal(invoice["tax_amount"])
    assert Decimal(body["purchases_subtotal"]) == Decimal(bill["subtotal_amount"])
    assert Decimal(body["input_vat"]) == Decimal(bill["tax_amount"])
    assert Decimal(body["net_vat_payable"]) == Decimal(body["output_vat"]) - Decimal(body["input_vat"])
    # Real business assertion: a company that sold more than it bought in
    # the period owes VAT (positive net payable), not a refund.
    assert Decimal(body["net_vat_payable"]) > 0


async def test_vat_summary_excludes_vendor_debit_notes_from_purchases(client):
    """Regression for a real reported bug (same defect class as the
    Dashboard's Purchases KPI): this report's purchases_stmt summed every
    posted VendorBill regardless of `bill_type`, so a Vendor Debit Note
    (a return to the vendor, positive `total_amount` mirroring the bill it
    reverses) inflated purchases_total/input_vat instead of being
    excluded, exactly like the sales side already excludes credit notes."""
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    bill = await _post_vendor_bill(client, headers, bill_date=today.isoformat())

    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill['id']}:debit-note",
        headers=headers,
        json={"reason": "Full return"},
    )
    assert debit_resp.status_code == 201, debit_resp.text

    resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Purchases/input VAT reflect only the original standard bill -- the
    # debit note must not add a second, ghost purchase on top of it.
    assert Decimal(body["purchases_subtotal"]) == Decimal(bill["subtotal_amount"])
    assert Decimal(body["input_vat"]) == Decimal(bill["tax_amount"])
    assert Decimal(body["purchases_total"]) == Decimal(bill["total_amount"])


async def test_vat_summary_excludes_out_of_range_and_unposted(client):
    _, headers = await _bootstrap_and_login(client)
    await _issue_sale(client, headers, invoice_date=date.today().isoformat())

    past_from = (date.today() - timedelta(days=3650)).isoformat()
    past_to = (date.today() - timedelta(days=3600)).isoformat()
    resp = await client.get(
        "/api/v1/reporting/vat-summary", headers=headers, params={"date_from": past_from, "date_to": past_to}
    )
    body = resp.json()
    assert Decimal(body["output_vat"]) == 0
    assert Decimal(body["net_vat_payable"]) == 0


async def test_vat_summary_export_pdf_and_excel(client):
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    await _issue_sale(client, headers, invoice_date=today.isoformat())

    pdf_resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "format": "pdf"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.content[:4] == b"%PDF"

    xlsx_resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "format": "xlsx", "lang": "en"},
    )
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.content[:2] == b"PK"


async def test_vat_summary_requires_permission(client):
    resp = await client.get(
        "/api/v1/reporting/vat-summary", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
    )
    assert resp.status_code == 401
