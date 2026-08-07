"""Integration smoke test for the Inventory Valuation report (Product
Owner audit: "what is my stock worth right now?" is a standard report in
every reference ERP and was entirely absent here, even though the costing
engine to answer it correctly already existed).

Exercises both costing methods, since they read different underlying
tables (`StockQuant.moving_avg_cost` for average, `StockLayer` for FIFO)
and a bug reading the wrong one for a company's actual method would
silently understate the report rather than error.
"""

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


async def test_no_stock_returns_empty_not_error(client):
    _, headers = await _bootstrap_and_login(client, valuation_method="average")
    resp = await client.get("/api/v1/reporting/inventory-valuation", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []
