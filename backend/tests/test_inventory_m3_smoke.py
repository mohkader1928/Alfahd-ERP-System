"""Integration smoke test for Backend M3 — Inventory.

Exercises UC-INV-01/02 (transfers, cycle counts) plus the Sales integration
wired back in this milestone: once a company has a default warehouse,
invoicing a stockable product deducts stock and posts a COGS entry
(FR-SAL-003, FR-INV-005), and insufficient stock blocks the sale (FR-INV-007).
"""

from datetime import date, timedelta

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


async def test_cycle_count_posts_one_net_journal_entry_across_lines(client):
    """A cycle count with multiple lines must post exactly ONE journal
    entry for the whole count, sized to the NET value of every line's
    increase/decrease combined -- not one entry per line. Each line still
    gets its own Stock Move (quantities can't be netted across different
    products), tagged move_type="adjustment" so it reads as a distinct
    document type from ordinary receipts/transfers."""
    _, headers = await _bootstrap_and_login(client)
    product_a = await _create_product(client, headers)
    product_b = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_a, "location_id": location_id, "qty": "10", "unit_cost": "20.00"},
    )
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_b, "location_id": location_id, "qty": "5", "unit_cost": "10.00"},
    )

    # Product A: counted 12 (system 10) -> +2 units * 20.00 = +40.00 increase.
    # Product B: counted 2 (system 5) -> -3 units * 10.00 = -30.00 decrease.
    # Net = +40.00 - 30.00 = +10.00 (a net increase).
    create_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": wh["warehouse"]["id"],
            "scheduled_date": "2026-04-05",
            "lines": [
                {"product_id": product_a, "location_id": location_id, "counted_qty": "12"},
                {"product_id": product_b, "location_id": location_id, "counted_qty": "2"},
            ],
        },
    )
    cycle_count_id = create_resp.json()["cycle_count"]["id"]

    je_before = (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json()

    approve_resp = await client.post(f"/api/v1/inventory/cycle-counts/{cycle_count_id}:approve", headers=headers)
    assert approve_resp.status_code == 200
    detail = approve_resp.json()
    # Both lines got their own stock move.
    assert all(line["stock_move_id"] is not None for line in detail["lines"])

    je_after = (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json()
    new_entries = [e for e in je_after if e["id"] not in {j["id"] for j in je_before}]
    assert len(new_entries) == 1  # exactly one entry for the whole count, not two
    assert new_entries[0]["reference"] == f"Cycle count {cycle_count_id}"

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    # Net Dr Inventory 10.00 (the +40 increase minus -30 decrease, in one entry).
    assert rows["1300"]["period_debit"] == "10.0000"

    moves = (await client.get("/api/v1/inventory/stock/moves", headers=headers, params={"product_id": product_a})).json()
    a_adjustment = next(m for m in moves if m["source_table"] == "cycle_count_line")
    assert a_adjustment["move_type"] == "adjustment"


async def test_cycle_count_net_zero_posts_no_journal_entry(client):
    """Two lines whose value changes exactly offset (one increase, one
    decrease of equal value) must still move real stock (both Stock Moves
    are created), but post NO journal entry at all -- a zero-amount entry
    would be a meaningless ledger row."""
    _, headers = await _bootstrap_and_login(client)
    product_a = await _create_product(client, headers)
    product_b = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_a, "location_id": location_id, "qty": "10", "unit_cost": "10.00"},
    )
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_b, "location_id": location_id, "qty": "10", "unit_cost": "10.00"},
    )

    # A: +2 units * 10.00 = +20.00. B: -2 units * 10.00 = -20.00. Net = 0.
    create_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": wh["warehouse"]["id"],
            "scheduled_date": "2026-04-06",
            "lines": [
                {"product_id": product_a, "location_id": location_id, "counted_qty": "12"},
                {"product_id": product_b, "location_id": location_id, "counted_qty": "8"},
            ],
        },
    )
    cycle_count_id = create_resp.json()["cycle_count"]["id"]

    je_before = (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json()

    approve_resp = await client.post(f"/api/v1/inventory/cycle-counts/{cycle_count_id}:approve", headers=headers)
    assert approve_resp.status_code == 200
    detail = approve_resp.json()
    assert all(line["stock_move_id"] is not None for line in detail["lines"])  # stock still moved

    je_after = (await client.get("/api/v1/accounting/journal-entries", headers=headers)).json()
    assert len(je_after) == len(je_before)  # no new entry posted


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


async def test_cardex_opening_balance_and_running_qty(client):
    """Bundle E -- standard product cardex (Owner-requested): a move dated
    before the report's date_from is folded into opening_qty, not shown as
    a line; a move within [date_from, date_to] appears with a running
    balance that carries opening_qty forward."""
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "5.00"},
    )

    # As-of yesterday: nothing had happened yet.
    before_resp = await client.get(
        "/api/v1/inventory/stock/cardex",
        headers=headers,
        params={"product_id": product_id, "date_from": yesterday, "date_to": yesterday},
    )
    assert before_resp.status_code == 200
    before = before_resp.json()
    assert before["opening_qty"] == "0.000000"
    assert before["lines"] == []
    assert before["closing_qty"] == "0.000000"

    # Today: the receive shows as a line, running_qty reflects it.
    today_resp = await client.get(
        "/api/v1/inventory/stock/cardex",
        headers=headers,
        params={"product_id": product_id, "date_from": today, "date_to": today},
    )
    today_data = today_resp.json()
    assert today_data["opening_qty"] == "0.000000"
    assert len(today_data["lines"]) == 1
    assert today_data["lines"][0]["signed_qty"] == "10.000000"
    assert today_data["lines"][0]["running_qty"] == "10.000000"
    assert today_data["closing_qty"] == "10.000000"

    # As-of tomorrow: today's receive is now folded into opening_qty.
    after_resp = await client.get(
        "/api/v1/inventory/stock/cardex",
        headers=headers,
        params={"product_id": product_id, "date_from": tomorrow, "date_to": tomorrow},
    )
    after = after_resp.json()
    assert after["opening_qty"] == "10.000000"
    assert after["lines"] == []
    assert after["closing_qty"] == "10.000000"


async def test_cardex_warehouse_filter_scopes_transfer_legs(client):
    """A transfer between two locations produces two Stock Moves (issue at
    source, receive at dest). Filtering the cardex to one warehouse must
    show only the leg that touches it."""
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh_a = await _create_warehouse(client, headers)
    location_a = wh_a["default_location"]["id"]
    wh_b_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Cardex Warehouse B"}
    )
    wh_b = wh_b_resp.json()
    location_b = wh_b["default_location"]["id"]

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_a, "qty": "20", "unit_cost": "3.00"},
    )
    await client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={"product_id": product_id, "source_location_id": location_a, "dest_location_id": location_b, "qty": "8"},
    )

    today = date.today().isoformat()

    cardex_a = (
        await client.get(
            "/api/v1/inventory/stock/cardex",
            headers=headers,
            params={"product_id": product_id, "date_from": today, "date_to": today, "warehouse_id": wh_a["warehouse"]["id"]},
        )
    ).json()
    assert cardex_a["closing_qty"] == "12.000000"  # 20 received - 8 transferred out

    cardex_b = (
        await client.get(
            "/api/v1/inventory/stock/cardex",
            headers=headers,
            params={"product_id": product_id, "date_from": today, "date_to": today, "warehouse_id": wh_b["warehouse"]["id"]},
        )
    ).json()
    assert cardex_b["closing_qty"] == "8.000000"  # only the transfer-in leg

    cardex_all = (
        await client.get(
            "/api/v1/inventory/stock/cardex",
            headers=headers,
            params={"product_id": product_id, "date_from": today, "date_to": today},
        )
    ).json()
    assert cardex_all["closing_qty"] == "20.000000"  # unfiltered: internal transfer nets to zero movement


async def test_cardex_source_table_filter(client):
    _, headers = await _bootstrap_and_login(client)
    product_id = await _create_product(client, headers)
    wh = await _create_warehouse(client, headers)
    location_id = wh["default_location"]["id"]
    today = date.today().isoformat()

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "6", "unit_cost": "1.00"},
    )
    create_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": wh["warehouse"]["id"],
            "scheduled_date": today,
            "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "9"}],
        },
    )
    await client.post(
        f"/api/v1/inventory/cycle-counts/{create_resp.json()['cycle_count']['id']}:approve", headers=headers
    )

    manual_only = (
        await client.get(
            "/api/v1/inventory/stock/cardex",
            headers=headers,
            params={"product_id": product_id, "date_from": today, "date_to": today, "source_table": "manual_receipt"},
        )
    ).json()
    assert len(manual_only["lines"]) == 1
    assert manual_only["lines"][0]["source_table"] == "manual_receipt"

    adjustment_only = (
        await client.get(
            "/api/v1/inventory/stock/cardex",
            headers=headers,
            params={"product_id": product_id, "date_from": today, "date_to": today, "source_table": "cycle_count_line"},
        )
    ).json()
    assert len(adjustment_only["lines"]) == 1
    assert adjustment_only["lines"][0]["source_table"] == "cycle_count_line"
    assert adjustment_only["lines"][0]["signed_qty"] == "3.000000"  # 9 counted - 6 system
