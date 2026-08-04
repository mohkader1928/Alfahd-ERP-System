"""Integration smoke test for Backend M3 — Inventory.

Exercises UC-INV-01/02 (transfers, cycle counts) plus the Sales integration
wired back in this milestone: once a company has a default warehouse,
invoicing a stockable product deducts stock and posts a COGS entry
(FR-SAL-003, FR-INV-005), and insufficient stock blocks the sale (FR-INV-007).
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, *, valuation_method="average"):
    payload = {
        "tenant_legal_name": "Inv Test Holding",
        "company_legal_name": "Inv Test Trading Co.",
        "company_legal_name_ar": "Inv Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": valuation_method,
        "admin_email": unique_email(),
        "admin_full_name": "Inv Test Admin",
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


async def _create_product(client, headers) -> str:
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Steel Beam", "sales_price": "1000.00"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_warehouse(client, headers) -> dict:
    resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Main Warehouse", "is_default": True}
    )
    assert resp.status_code == 201
    return resp.json()


async def test_receive_stock_and_query_quant(client):
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]

    receive_resp = await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "50", "unit_cost": "10.00"},
    )
    assert receive_resp.status_code == 201
    assert receive_resp.json()["move_type"] == "receipt"

    quants_resp = await client.get("/api/v1/inventory/stock/quants", headers=headers)
    assert quants_resp.status_code == 200
    quants = quants_resp.json()
    assert len(quants) == 1
    assert quants[0]["qty_on_hand"] == "50.000000"
    assert quants[0]["moving_avg_cost"] == "10.0000"


async def test_creating_second_default_warehouse_clears_previous_default(client):
    """Regression: nothing previously unset the old default when a second
    warehouse was created with is_default=True, so a company could end up
    with two default warehouses -- and WarehouseRepository.get_default_for_company's
    scalar_one_or_none() would then raise instead of returning cleanly."""
    _, headers = await _bootstrap_and_login(client)
    await _create_warehouse(client, headers)  # "Main Warehouse", is_default=True

    resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Second Warehouse", "is_default": True}
    )
    assert resp.status_code == 201

    list_resp = await client.get("/api/v1/inventory/warehouses", headers=headers)
    defaults = [w for w in list_resp.json() if w["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "Second Warehouse"


async def test_set_default_warehouse_switches_default_and_unblocks_receipt(client):
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh1 = await _create_warehouse(client, headers)  # default

    wh2_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Secondary Warehouse", "is_default": False}
    )
    wh2 = wh2_resp.json()

    set_default_resp = await client.post(
        f"/api/v1/inventory/warehouses/{wh2['warehouse']['id']}:set-default", headers=headers
    )
    assert set_default_resp.status_code == 200
    assert set_default_resp.json()["is_default"] is True

    list_resp = await client.get("/api/v1/inventory/warehouses", headers=headers)
    warehouses = {w["id"]: w for w in list_resp.json()}
    assert warehouses[wh1["warehouse"]["id"]]["is_default"] is False
    assert warehouses[wh2["warehouse"]["id"]]["is_default"] is True

    # A purchasing goods-receipt flow (which requires a default warehouse)
    # now resolves against the newly-promoted warehouse's location.
    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Set-Default Vendor", "is_vendor": True}
    )
    vendor_id = vendor_resp.json()["id"]
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [
                {
                    "product_id": product_id,
                    "qty": "1",
                    "unit_price": "10.00",
                    "tax_rate_id": "00000000-0000-0000-0000-000000000001",
                }
            ],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_line_id = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()["lines"][0]["id"]

    receipt_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "1"}]},
    )
    assert receipt_resp.status_code == 201
    assert receipt_resp.json()["warehouse_id"] == wh2["warehouse"]["id"]


async def test_set_default_warehouse_cross_company_404(client):
    _, headers_a = await _bootstrap_and_login(client)
    wh = await _create_warehouse(client, headers_a)

    _, headers_b = await _bootstrap_and_login(client)
    resp = await client.post(
        f"/api/v1/inventory/warehouses/{wh['warehouse']['id']}:set-default", headers=headers_b
    )
    assert resp.status_code == 404


async def test_transfer_moves_stock_between_locations(client):
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    source_location_id = wh["default_location"]["id"]

    wh2_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Secondary Warehouse", "is_default": False}
    )
    dest_location_id = wh2_resp.json()["default_location"]["id"]

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": source_location_id, "qty": "20", "unit_cost": "5.00"},
    )

    transfer_resp = await client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "product_id": product_id,
            "source_location_id": source_location_id,
            "dest_location_id": dest_location_id,
            "qty": "8",
        },
    )
    assert transfer_resp.status_code == 201
    moves = transfer_resp.json()
    assert len(moves) == 2

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    by_location = {q["location_id"]: q["qty_on_hand"] for q in quants}
    assert by_location[source_location_id] == "12.000000"
    assert by_location[dest_location_id] == "8.000000"


async def test_transfer_blocks_when_insufficient_stock(client):
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    source_location_id = wh["default_location"]["id"]
    wh2_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Secondary Warehouse 2"}
    )
    dest_location_id = wh2_resp.json()["default_location"]["id"]

    resp = await client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "product_id": product_id,
            "source_location_id": source_location_id,
            "dest_location_id": dest_location_id,
            "qty": "5",
        },
    )
    assert resp.status_code == 422


async def test_cycle_count_posts_adjustment_and_journal_entry(client):
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "20.00"},
    )

    create_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": wh["warehouse"]["id"],
            "scheduled_date": "2026-04-01",
            "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "7"}],
        },
    )
    assert create_resp.status_code == 201
    cycle_count_id = create_resp.json()["cycle_count"]["id"]
    assert create_resp.json()["lines"][0]["system_qty"] == "10.000000"

    approve_resp = await client.post(f"/api/v1/inventory/cycle-counts/{cycle_count_id}:approve", headers=headers)
    assert approve_resp.status_code == 200
    assert approve_resp.json()["cycle_count"]["status"] == "approved"

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    assert quants[0]["qty_on_hand"] == "7.000000"

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    assert rows["1300"]["total_credit"] == "60.0000"  # 3 units * 20.00 written off

    list_resp = await client.get("/api/v1/inventory/cycle-counts", headers=headers)
    assert list_resp.status_code == 200
    assert any(c["id"] == cycle_count_id for c in list_resp.json())

    detail_resp = await client.get(f"/api/v1/inventory/cycle-counts/{cycle_count_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["cycle_count"]["status"] == "approved"
    assert detail["lines"][0]["counted_qty"] == "7.000000"
    assert detail["lines"][0]["stock_move_id"] is not None


async def test_cycle_count_not_visible_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers_a)
    wh = await _create_warehouse(client, headers_a)
    location_id = wh["default_location"]["id"]

    create_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers_a,
        json={
            "warehouse_id": wh["warehouse"]["id"],
            "scheduled_date": "2026-04-01",
            "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "5"}],
        },
    )
    cycle_count_id = create_resp.json()["cycle_count"]["id"]

    _, headers_b = await _bootstrap_and_login(client)
    list_resp = await client.get("/api/v1/inventory/cycle-counts", headers=headers_b)
    assert all(c["id"] != cycle_count_id for c in list_resp.json())
    detail_resp = await client.get(f"/api/v1/inventory/cycle-counts/{cycle_count_id}", headers=headers_b)
    assert detail_resp.status_code == 404


async def test_sales_invoice_deducts_stock_when_warehouse_configured(client):
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "5", "unit_cost": "600.00"},
    )

    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "B2B Buyer", "is_customer": True, "vat_number": unique_vat()}
    )
    partner_id = partner_resp.json()["id"]

    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-04-01",
            "lines": [{"product_id": product_id, "qty": "2", "unit_price": "1000.00", "tax_rate_id": "00000000-0000-0000-0000-000000000001"}],
        },
    )
    quotation_id = quote_resp.json()["id"]
    order_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    order_id = order_resp.json()["id"]

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    assert quants[0]["qty_on_hand"] == "3.000000"  # 5 received - 2 sold

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    assert rows["5100"]["total_debit"] == "1200.0000"  # COGS: 2 * 600.00
    assert rows["1300"]["total_credit"] == "1200.0000"


async def test_fifo_valuation_consumes_oldest_layer_first(client):
    _, headers = await _bootstrap_and_login(client, valuation_method="fifo")
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]

    # Two receipts at different costs — FIFO must consume the first (cheaper)
    # layer before touching the second.
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "5.00"},
    )
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "8.00"},
    )

    # Transfer 12 units out — should consume all 10 @5.00 + 2 @8.00 = 66.00 total cost.
    wh2_resp = await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "FIFO Dest"})
    dest_location_id = wh2_resp.json()["default_location"]["id"]

    transfer_resp = await client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "product_id": product_id,
            "source_location_id": location_id,
            "dest_location_id": dest_location_id,
            "qty": "12",
        },
    )
    assert transfer_resp.status_code == 201
    moves = transfer_resp.json()
    issue_move = next(m for m in moves if m["source_location_id"] == location_id)
    # Weighted unit cost of the issued 12 units: 66.00 / 12 = 5.50
    assert issue_move["unit_cost"] == "5.5000"

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    by_location = {q["location_id"]: q["qty_on_hand"] for q in quants}
    assert by_location[location_id] == "8.000000"  # 20 received - 12 issued


async def test_sales_invoice_blocked_when_insufficient_stock(client):
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    await _create_warehouse(client, headers)  # no stock received

    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "B2B Buyer 2", "is_customer": True, "vat_number": unique_vat()}
    )
    partner_id = partner_resp.json()["id"]

    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-04-01",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": "00000000-0000-0000-0000-000000000001"}],
        },
    )
    quotation_id = quote_resp.json()["id"]
    order_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    order_id = order_resp.json()["id"]

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 422


async def test_list_stock_moves(client):
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]

    receive_resp = await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "30", "unit_cost": "4.00"},
    )
    move_id = receive_resp.json()["id"]

    moves_resp = await client.get("/api/v1/inventory/stock/moves", headers=headers)
    assert moves_resp.status_code == 200
    moves = moves_resp.json()
    assert any(m["id"] == move_id for m in moves)
    receipt = next(m for m in moves if m["id"] == move_id)
    assert receipt["move_type"] == "receipt"
    assert receipt["qty"] == "30.000000"


async def test_list_stock_moves_filtered_by_product(client):
    _, headers = await _bootstrap_and_login(client)
    product_a = await _create_product(client, headers)
    product_b = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_a, "location_id": location_id, "qty": "10", "unit_cost": "4.00"},
    )
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_b, "location_id": location_id, "qty": "5", "unit_cost": "2.00"},
    )

    moves_resp = await client.get(
        "/api/v1/inventory/stock/moves", headers=headers, params={"product_id": product_a}
    )
    assert moves_resp.status_code == 200
    moves = moves_resp.json()
    assert len(moves) == 1
    assert moves[0]["product_id"] == product_a
