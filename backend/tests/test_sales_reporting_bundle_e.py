"""Integration smoke test for Bundle E — Sales Reporting (by customer/product/period).

Exercises FR-RPT: cross-module Sales reporting queries added alongside the
Trial Balance Opening/Period/Closing redesign. Mirrors the bootstrap/login
pattern in test_reporting_m5_smoke.py.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "SalesRpt Test Holding",
        "company_legal_name": "SalesRpt Test Trading Co.",
        "company_legal_name_ar": "SalesRpt Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "SalesRpt Test Admin",
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


async def _invoice_one_sale(client, headers, *, partner_name, product_name, qty, unit_price, invoice_date):
    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        # No vat_number -> simplified invoice -> "pending_submission" status
        # immediately (synchronous), matching the report's finalized-status filter.
        json={"name": partner_name, "is_customer": True},
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": product_name, "sales_price": unit_price},
    )
    product_id = product_resp.json()["id"]

    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": invoice_date,
            "lines": [{"product_id": product_id, "qty": qty, "unit_price": unit_price, "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    quotation_id = quote_resp.json()["id"]
    order_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    order_id = order_resp.json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    return partner_id, product_id, invoice_resp.json()["invoice"]


async def test_sales_by_customer_aggregates_finalized_invoices(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id, _, invoice = await _invoice_one_sale(
        client, headers,
        partner_name="Report Customer A", product_name="Widget", qty="2", unit_price="100.00",
        invoice_date="2026-06-01",
    )
    assert invoice["status"] == "pending_submission"

    resp = await client.get(
        "/api/v1/reporting/sales/by-customer",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 200
    rows = {row["partner_id"]: row for row in resp.json()}
    row = rows[partner_id]
    assert row["invoice_count"] == 1
    assert row["subtotal"] == "200.0000"
    assert row["tax_amount"] == "30.0000"
    assert row["total"] == "230.0000"


async def test_sales_by_product_aggregates_line_quantities(client):
    _, headers = await _bootstrap_and_login(client)
    _, product_id, _ = await _invoice_one_sale(
        client, headers,
        partner_name="Report Customer B", product_name="Gadget", qty="3", unit_price="50.00",
        invoice_date="2026-06-05",
    )

    resp = await client.get(
        "/api/v1/reporting/sales/by-product",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 200
    rows = {row["product_id"]: row for row in resp.json()}
    row = rows[product_id]
    assert row["qty_sold"] == "3.000000"
    assert row["subtotal"] == "150.0000"
    assert row["total"] == "172.5000"  # 150 + 15% VAT


async def test_sales_by_period_groups_by_calendar_month(client):
    # SalesInvoiceService now inherits the order's own date (order_date,
    # itself carried from the quotation's quote_date) rather than forcing
    # date.today() -- so the invoice's real period follows the date
    # actually entered on the quotation below, not the day the test runs.
    _, headers = await _bootstrap_and_login(client)
    await _invoice_one_sale(
        client, headers,
        partner_name="Report Customer C", product_name="Thing", qty="1", unit_price="1000.00",
        invoice_date="2026-07-10",
    )

    resp = await client.get(
        "/api/v1/reporting/sales/by-period",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 200
    rows = {row["period_label"]: row for row in resp.json()}
    assert "2026-07" in rows
    assert rows["2026-07"]["total"] == "1150.0000"


async def test_sales_reports_excludes_out_of_range_dates(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id, _, _ = await _invoice_one_sale(
        client, headers,
        partner_name="Report Customer D", product_name="OutOfRange", qty="1", unit_price="10.00",
        invoice_date="2026-01-01",
    )

    resp = await client.get(
        "/api/v1/reporting/sales/by-customer",
        headers=headers,
        params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200
    assert all(row["partner_id"] != partner_id for row in resp.json())


async def test_sales_reports_require_permission(client):
    resp = await client.get(
        "/api/v1/reporting/sales/by-customer", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
    )
    assert resp.status_code == 401


async def test_sales_reports_export_pdf_and_excel(client):
    """Standard Reporting Framework — Sales reports must also serve real
    PDF/Excel, matching every other report."""
    _, headers = await _bootstrap_and_login(client)
    await _invoice_one_sale(
        client, headers,
        partner_name="Export Report Customer", product_name="Export Widget", qty="2", unit_price="100.00",
        invoice_date="2026-06-01",
    )
    params = {"date_from": "2026-01-01", "date_to": "2026-12-31"}

    for path in ("by-customer", "by-product", "by-period"):
        pdf_resp = await client.get(
            f"/api/v1/reporting/sales/{path}", headers=headers, params={**params, "format": "pdf"}
        )
        assert pdf_resp.status_code == 200, pdf_resp.text
        assert pdf_resp.content[:4] == b"%PDF"

        xlsx_resp = await client.get(
            f"/api/v1/reporting/sales/{path}",
            headers=headers,
            params={**params, "format": "xlsx", "lang": "en"},
        )
        assert xlsx_resp.status_code == 200, xlsx_resp.text
        assert xlsx_resp.content[:2] == b"PK"
