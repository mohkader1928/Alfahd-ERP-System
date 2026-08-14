"""Owner request: show the live on-hand balance next to a product line on
Quotation/Sales Order/Sales Invoice/Purchase Order/Transfer, scoped to
that document's own warehouse — so the user sees what they already have
before buying, selling, or moving more of it. Covers the new
GET /inventory/stock/balance endpoint, the warehouse_id field added to
Quotation/SalesOrder/SalesInvoice/PurchaseOrder, and that stock actually
moves through the chosen warehouse (not always the company default) end
to end: Quotation -> confirm -> SalesOrder -> invoice -> stock deduction,
and PurchaseOrder -> goods receipt -> stock receipt.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Warehouse Balance Test Holding",
        "company_legal_name": "Warehouse Balance Test Trading Co.",
        "company_legal_name_ar": "Warehouse Balance Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Warehouse Balance Test Admin",
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


async def _two_warehouses(client, headers):
    """Returns (default_warehouse_id, default_location_id, secondary_warehouse_id, secondary_location_id)."""
    w1 = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True}
    )
    w1_body = w1.json()
    w2 = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Secondary", "is_default": False}
    )
    w2_body = w2.json()
    return (
        w1_body["warehouse"]["id"],
        w1_body["default_location"]["id"],
        w2_body["warehouse"]["id"],
        w2_body["default_location"]["id"],
    )


async def _create_product(client, headers, name="Balance Product"):
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"WB-{unique_vat()[:8]}", "name": name, "sales_price": "50.00"},
    )
    return resp.json()["id"]


async def test_stock_balance_endpoint_is_scoped_to_one_warehouse(client):
    _, headers = await _bootstrap_and_login(client)
    _, loc_a, wh_b, loc_b = await _two_warehouses(client, headers)
    product_id = await _create_product(client, headers)

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": loc_b, "qty": "25", "unit_cost": "10.00"},
    )

    balance_b = await client.get(
        "/api/v1/inventory/stock/balance",
        headers=headers,
        params={"product_id": product_id, "warehouse_id": wh_b},
    )
    assert balance_b.status_code == 200
    assert balance_b.json()["qty_on_hand"] == "25.000000"

    # A product never received into warehouse A reads as zero there, not
    # leaking warehouse B's stock into an unrelated warehouse's balance.
    wh_a_resp = await client.get("/api/v1/inventory/warehouses", headers=headers)
    wh_a = next(w["id"] for w in wh_a_resp.json() if w["is_default"])
    balance_a = await client.get(
        "/api/v1/inventory/stock/balance",
        headers=headers,
        params={"product_id": product_id, "warehouse_id": wh_a},
    )
    assert balance_a.json()["qty_on_hand"] == "0.000000"


async def test_quotation_warehouse_carries_through_order_to_invoice_and_deducts_correct_warehouse(client):
    _, headers = await _bootstrap_and_login(client)
    wh_a, loc_a, wh_b, loc_b = await _two_warehouses(client, headers)
    product_id = await _create_product(client, headers)

    # Stock only exists in warehouse B — if the invoice deducted from the
    # company default (warehouse A) instead of the quotation's own choice,
    # this would raise InsufficientStockError.
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": loc_b, "qty": "10", "unit_cost": "20.00"},
    )

    customer_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Balance Customer", "is_customer": True}
    )
    customer_id = customer_resp.json()["id"]

    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": customer_id,
            "quote_date": "2026-06-01",
            "warehouse_id": wh_b,
            "lines": [{"product_id": product_id, "qty": "3", "unit_price": "50.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert quote_resp.status_code == 201
    assert quote_resp.json()["warehouse_id"] == wh_b
    quotation_id = quote_resp.json()["id"]

    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    assert confirm_resp.status_code == 200
    order = confirm_resp.json()
    assert order["warehouse_id"] == wh_b
    order_id = order["id"]

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    invoice_body = invoice_resp.json()["invoice"]
    assert invoice_body["warehouse_id"] == wh_b

    balance_b = await client.get(
        "/api/v1/inventory/stock/balance",
        headers=headers,
        params={"product_id": product_id, "warehouse_id": wh_b},
    )
    assert balance_b.json()["qty_on_hand"] == "7.000000"  # 10 received - 3 sold

    balance_a = await client.get(
        "/api/v1/inventory/stock/balance",
        headers=headers,
        params={"product_id": product_id, "warehouse_id": wh_a},
    )
    assert balance_a.json()["qty_on_hand"] == "0.000000"  # untouched


async def test_quotation_without_warehouse_still_deducts_from_company_default(client):
    """Backward compatibility: a quotation that never sets warehouse_id
    (the pre-feature shape, still valid — the field is optional) keeps
    working exactly as it did before this feature, falling back to the
    company's default warehouse for the actual stock deduction."""
    _, headers = await _bootstrap_and_login(client)
    wh_a, loc_a, _wh_b, _loc_b = await _two_warehouses(client, headers)
    product_id = await _create_product(client, headers)

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": loc_a, "qty": "5", "unit_cost": "20.00"},
    )

    customer_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Legacy Customer", "is_customer": True}
    )
    customer_id = customer_resp.json()["id"]

    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": customer_id,
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "2", "unit_price": "50.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert quote_resp.json()["warehouse_id"] is None
    quotation_id = quote_resp.json()["id"]

    order_id = (await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201

    balance_a = await client.get(
        "/api/v1/inventory/stock/balance",
        headers=headers,
        params={"product_id": product_id, "warehouse_id": wh_a},
    )
    assert balance_a.json()["qty_on_hand"] == "3.000000"  # 5 received - 2 sold, from the default warehouse


async def test_purchase_order_warehouse_carries_through_to_goods_receipt(client):
    _, headers = await _bootstrap_and_login(client)
    wh_a, _loc_a, wh_b, _loc_b = await _two_warehouses(client, headers)
    product_id = await _create_product(client, headers)

    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Balance Vendor", "is_vendor": True}
    )
    vendor_id = vendor_resp.json()["id"]

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-06-01",
            "warehouse_id": wh_b,
            "lines": [{"product_id": product_id, "qty": "8", "unit_price": "15.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert po_resp.status_code == 201
    assert po_resp.json()["warehouse_id"] == wh_b
    order_id = po_resp.json()["id"]

    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]

    receipt_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "8"}]},
    )
    assert receipt_resp.status_code == 201
    assert receipt_resp.json()["warehouse_id"] == wh_b  # received into the PO's own warehouse, not the default

    balance_b = await client.get(
        "/api/v1/inventory/stock/balance",
        headers=headers,
        params={"product_id": product_id, "warehouse_id": wh_b},
    )
    assert balance_b.json()["qty_on_hand"] == "8.000000"

    balance_a = await client.get(
        "/api/v1/inventory/stock/balance",
        headers=headers,
        params={"product_id": product_id, "warehouse_id": wh_a},
    )
    assert balance_a.json()["qty_on_hand"] == "0.000000"  # default warehouse untouched
