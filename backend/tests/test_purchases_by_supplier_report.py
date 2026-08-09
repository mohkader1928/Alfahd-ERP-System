"""Purchases by Supplier report (P0-3, 3-Day Brief) -- mirrors
test_sales_reporting_bundle_e.py's shape, on top of the procure-to-pay
bootstrap already established in test_vendor_debit_note.py.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client, label="PurchRpt"):
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
    branch_id = boot_resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, headers


async def _cash_account_id(client, headers) -> str:
    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    return next(a["id"] for a in accounts if a["code"] == "1100")


async def _create_posted_bill(client, headers, *, vendor_name, product_name, qty, unit_price, bill_date) -> tuple[str, str]:
    """Returns (bill_id, vendor_id) for a fully procured-to-pay, posted bill."""
    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": vendor_name, "is_vendor": True}
    )
    vendor_id = vendor_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": product_name, "sales_price": unit_price},
    )
    product_id = product_resp.json()["id"]
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True})

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": bill_date,
            "lines": [{"product_id": product_id, "qty": qty, "unit_price": unit_price, "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]

    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": qty}]},
    )
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "INV-RPT", "lines": [{"purchase_order_line_id": po_line_id, "qty": qty, "unit_price": unit_price}]},
    )
    bill_id = bill_resp.json()["id"]
    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)
    assert approve_resp.json()["status"] == "posted"
    return bill_id, vendor_id


async def test_purchases_by_supplier_aggregates_posted_bills(client):
    _, headers = await _bootstrap_and_login(client, "Aggregate")
    bill_id, vendor_id = await _create_posted_bill(
        client, headers, vendor_name="Report Vendor A", product_name="Widget", qty="2", unit_price="100.00",
        bill_date="2026-06-01",
    )

    resp = await client.get(
        "/api/v1/reporting/purchasing/by-supplier",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 200
    rows = {row["partner_id"]: row for row in resp.json()}
    row = rows[vendor_id]
    assert row["bill_count"] == 1
    assert row["subtotal"] == "200.0000"
    assert row["tax_amount"] == "30.0000"
    assert row["total"] == "230.0000"
    assert row["adjustments"] == "0"
    assert row["net_total"] == "230.0000"


async def test_purchases_by_supplier_shows_debit_note_as_adjustment(client):
    _, headers = await _bootstrap_and_login(client, "Adjustment")
    bill_id, vendor_id = await _create_posted_bill(
        client, headers, vendor_name="Report Vendor B", product_name="Steel", qty="10", unit_price="20.00",
        bill_date="2026-06-01",
    )
    await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=headers, json={"reason": "Damaged goods"}
    )

    resp = await client.get(
        "/api/v1/reporting/purchasing/by-supplier",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["partner_id"]: row for row in resp.json()}
    row = rows[vendor_id]
    # The debit note itself is bill_type="debit_note" -- excluded from the
    # main "total" aggregate (mirrors sales excluding credit_note), but
    # shown as its own "adjustments" column and folded into net_total.
    assert row["total"] == "230.0000"
    assert row["adjustments"] == "230.0000"
    assert row["net_total"] == "0.0000"


async def test_purchases_by_supplier_reflects_payments_and_ap_balance(client):
    _, headers = await _bootstrap_and_login(client, "Balance")
    bill_id, vendor_id = await _create_posted_bill(
        client, headers, vendor_name="Report Vendor C", product_name="Bolts", qty="5", unit_price="40.00",
        bill_date="2026-06-01",
    )
    cash_id = await _cash_account_id(client, headers)

    # Partial payment: bill total = 5*40*1.15 = 230.00, pay 100.00.
    await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "payment_type": "vendor",
            "payment_date": "2026-06-10",
            "amount": "100.00",
            "account_id": cash_id,
            "allocations": [{"vendor_bill_id": bill_id, "amount": "100.00"}],
        },
    )

    resp = await client.get(
        "/api/v1/reporting/purchasing/by-supplier",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["partner_id"]: row for row in resp.json()}
    row = rows[vendor_id]
    assert row["payments_made"] == "100.0000"
    assert row["balance"] == "130.0000"  # 230 - 100

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    ap_row = next(r for r in trial_balance.json() if r["account_code"] == "2100")
    ap_net = float(ap_row["total_credit"]) - float(ap_row["total_debit"])
    assert ap_net == 130.00  # report balance reconciles with the Trial Balance's AP


async def test_purchases_by_supplier_filters_by_partner(client):
    _, headers = await _bootstrap_and_login(client, "Filter")
    _, vendor_a = await _create_posted_bill(
        client, headers, vendor_name="Filter Vendor A", product_name="Item A", qty="1", unit_price="10.00",
        bill_date="2026-06-01",
    )
    _, vendor_b = await _create_posted_bill(
        client, headers, vendor_name="Filter Vendor B", product_name="Item B", qty="1", unit_price="20.00",
        bill_date="2026-06-01",
    )

    resp = await client.get(
        "/api/v1/reporting/purchasing/by-supplier",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31", "partner_id": vendor_a},
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["partner_id"] == vendor_a
    assert all(row["partner_id"] != vendor_b for row in rows)


async def test_purchases_by_supplier_excludes_out_of_range_dates(client):
    _, headers = await _bootstrap_and_login(client, "OutOfRange")
    _, vendor_id = await _create_posted_bill(
        client, headers, vendor_name="Report Vendor D", product_name="OutOfRange Item", qty="1", unit_price="10.00",
        bill_date="2026-01-01",
    )

    resp = await client.get(
        "/api/v1/reporting/purchasing/by-supplier",
        headers=headers,
        params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200
    assert all(row["partner_id"] != vendor_id for row in resp.json())


async def test_purchases_by_supplier_requires_permission(client):
    resp = await client.get(
        "/api/v1/reporting/purchasing/by-supplier", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
    )
    assert resp.status_code == 401


async def test_purchases_by_supplier_export_pdf_and_excel(client):
    _, headers = await _bootstrap_and_login(client, "Export")
    await _create_posted_bill(
        client, headers, vendor_name="Export Report Vendor", product_name="Export Widget", qty="2", unit_price="100.00",
        bill_date="2026-06-01",
    )
    params = {"date_from": "2026-01-01", "date_to": "2026-12-31"}

    pdf_resp = await client.get(
        "/api/v1/reporting/purchasing/by-supplier", headers=headers, params={**params, "format": "pdf"}
    )
    assert pdf_resp.status_code == 200, pdf_resp.text
    assert pdf_resp.content[:4] == b"%PDF"

    xlsx_resp = await client.get(
        "/api/v1/reporting/purchasing/by-supplier",
        headers=headers,
        params={**params, "format": "xlsx", "lang": "en"},
    )
    assert xlsx_resp.status_code == 200, xlsx_resp.text
    assert xlsx_resp.content[:2] == b"PK"
