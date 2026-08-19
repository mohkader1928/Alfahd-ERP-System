"""Integration smoke test for the Inventory Valuation report (Product
Owner audit: "what is my stock worth right now?" is a standard report in
every reference ERP and was entirely absent here, even though the costing
engine to answer it correctly already existed).

Exercises both costing methods, since they read different underlying
tables (`StockQuant.moving_avg_cost` for average, `StockLayer` for FIFO)
and a bug reading the wrong one for a company's actual method would
silently understate the report rather than error.
"""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client, *, valuation_method: str):
    payload = {
        "tenant_legal_name": "Valuation Test Holding",
        "company_legal_name": "Valuation Test Trading Co.",
        "company_legal_name_ar": "Valuation Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": valuation_method,
        "admin_email": unique_email(),
        "admin_full_name": "Valuation Test Admin",
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


async def _receive_stock(client, headers, *, qty: str, unit_price: str):
    warehouse_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Valuation Warehouse", "is_default": True}
    )
    warehouse = warehouse_resp.json()["warehouse"]
    vendor = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Valuation Vendor", "is_vendor": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"VAL-{unique_vat()[:8]}", "name": "Valuation Product", "cost_price": unit_price},
    )
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor.json()["id"],
            "order_date": "2026-06-01",
            "lines": [{"product_id": product.json()["id"], "qty": qty, "unit_price": unit_price, "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    receipt_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": qty}]},
    )
    assert receipt_resp.status_code == 201
    return warehouse, product.json()


async def test_average_method_valuation_from_moving_avg_cost(client):
    _, headers = await _bootstrap_and_login(client, valuation_method="average")
    warehouse, product = await _receive_stock(client, headers, qty="100", unit_price="20.00")

    resp = await client.get("/api/v1/reporting/inventory-valuation", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["product_id"] == product["id"]
    assert row["warehouse_id"] == warehouse["id"]
    assert row["qty_on_hand"] == "100.000000"
    assert row["unit_cost"] == "20.0000"
    assert row["total_value"] == "2000.0000"


async def test_fifo_method_valuation_from_stock_layers(client):
    _, headers = await _bootstrap_and_login(client, valuation_method="fifo")
    # Two receipts at different costs -- FIFO must sum both layers, not
    # just reflect the latest cost (which is exactly what would happen if
    # this report read StockQuant.moving_avg_cost for a FIFO company).
    warehouse1, product1 = await _receive_stock(client, headers, qty="10", unit_price="5.00")

    resp = await client.get("/api/v1/reporting/inventory-valuation", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["qty_on_hand"] == "10.000000"
    assert rows[0]["unit_cost"] == "5.0000"
    assert rows[0]["total_value"] == "50.0000"


async def test_warehouse_filter_narrows_results(client):
    _, headers = await _bootstrap_and_login(client, valuation_method="average")
    warehouse, _ = await _receive_stock(client, headers, qty="10", unit_price="5.00")

    other_warehouse = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Other Warehouse", "is_default": False}
    )

    matching = await client.get(
        "/api/v1/reporting/inventory-valuation", headers=headers, params={"warehouse_id": warehouse["id"]}
    )
    assert len(matching.json()) == 1

    non_matching = await client.get(
        "/api/v1/reporting/inventory-valuation",
        headers=headers,
        params={"warehouse_id": other_warehouse.json()["warehouse"]["id"]},
    )
    assert non_matching.json() == []


async def test_export_pdf_and_excel(client):
    _, headers = await _bootstrap_and_login(client, valuation_method="average")
    await _receive_stock(client, headers, qty="10", unit_price="5.00")

    pdf_resp = await client.get(
        "/api/v1/reporting/inventory-valuation", headers=headers, params={"format": "pdf"}
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.content[:4] == b"%PDF"

    xlsx_resp = await client.get(
        "/api/v1/reporting/inventory-valuation", headers=headers, params={"format": "xlsx", "lang": "en"}
    )
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.content[:2] == b"PK"


async def test_requires_permission(client):
    resp = await client.get("/api/v1/reporting/inventory-valuation")
    assert resp.status_code == 401


async def test_reconciliation_matches_gl_after_a_real_receipt(client):
    """Owner-reported finding (شركة المحمود, 2026-08-19): confirms the new
    /inventory-reconciliation endpoint independently computes both sides
    and reports MATCHED for the ordinary case -- a receipt's GL posting
    (Dr Inventory / Cr GRNI, via the goods-receipt flow) and its
    valuation-report value must agree."""
    _, headers = await _bootstrap_and_login(client, valuation_method="average")
    await _receive_stock(client, headers, qty="100", unit_price="20.00")

    resp = await client.get("/api/v1/reporting/inventory-reconciliation", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["gl_balance"] == "2000.0000"
    assert body["valuation_total"] == "2000.0000"
    assert body["difference"] == "0.0000"
    assert body["matched"] is True


async def test_reconciliation_requires_permission(client):
    resp = await client.get("/api/v1/reporting/inventory-reconciliation")
    assert resp.status_code == 401


async def test_no_stock_returns_empty_not_error(client):
    _, headers = await _bootstrap_and_login(client, valuation_method="average")
    resp = await client.get("/api/v1/reporting/inventory-valuation", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_valuation_reconciles_with_trial_balance_when_stock_goes_negative(client):
    """Regression for a real production data-integrity bug, found live
    against a real company: this report's total silently diverged from
    Trial Balance's Inventory (1300) balance. Root cause -- a Vendor
    Debit Note return calls `InventoryService.issue_stock(...,
    allow_negative=True)` (FR-INV-007 override in
    purchasing/application/services.py), which can legitimately drive a
    product/location's `qty_on_hand` negative while posting the exact
    same cost to the GL. This report used to filter `qty_on_hand > 0`
    before summing, which silently dropped that negative position
    instead of netting it in -- overstating the report by exactly the
    value of the excluded row. Scenario: receive 100 units @ 20.00 (GL
    +2000), sell 80 (GL -1600 COGS-side inventory credit, 20 left on
    hand), then fully return the original 100-unit bill to the vendor --
    the return can only find 20 physically on hand, so the location goes
    to -80. Trial Balance and this report must still agree exactly."""
    _, headers = await _bootstrap_and_login(client, valuation_method="average")

    vendor = await client.post("/api/v1/identity/partners", headers=headers, json={"name": "Neg Vendor", "is_vendor": True})
    customer = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Neg Customer", "is_customer": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"NEG-{unique_vat()[:8]}", "name": "Negative Stock Product", "cost_price": "20.00", "sales_price": "50.00"},
    )
    product_id = product.json()["id"]
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True})

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor.json()["id"],
            "order_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "100", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "100"}]},
    )
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "INV-1", "lines": [{"purchase_order_line_id": po_line_id, "qty": "100", "unit_price": "20.00"}]},
    )
    bill_id = bill_resp.json()["id"]
    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)
    assert approve_resp.json()["status"] == "posted"

    # Sell 80 of the 100 received units, leaving 20 on hand.
    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": customer.json()["id"],
            "quote_date": "2026-06-05",
            "lines": [{"product_id": product_id, "qty": "80", "unit_price": "50.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert quote_resp.status_code == 201, quote_resp.text
    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)
    assert confirm_resp.status_code == 200, confirm_resp.text
    sales_order_id = confirm_resp.json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{sales_order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text

    # Full-bill return to vendor -- returns all 100 units even though only
    # 20 remain on hand, driving that location to -80 (allow_negative=True).
    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "Full return after partial sale"},
    )
    assert debit_resp.status_code == 201, debit_resp.text

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    qty_on_hand = next(q["qty_on_hand"] for q in quants if q["product_id"] == product_id)
    assert qty_on_hand == "-80.000000"

    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    inventory_account_id = next(a["id"] for a in accounts if a["code"] == "1300")
    tb_resp = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert tb_resp.status_code == 200, tb_resp.text
    tb_row = next(r for r in tb_resp.json() if r["account_id"] == inventory_account_id)
    gl_balance = Decimal(tb_row["closing_balance"])

    valuation_resp = await client.get("/api/v1/reporting/inventory-valuation", headers=headers)
    assert valuation_resp.status_code == 200, valuation_resp.text
    valuation_total = sum((Decimal(row["total_value"]) for row in valuation_resp.json()), Decimal("0"))

    assert valuation_total == gl_balance == Decimal("-1600.0000")
