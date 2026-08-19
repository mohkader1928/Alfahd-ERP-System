"""Inventory Valuation vs Trial Balance reconciliation fix (2026-08-19),
reported by the Owner against شركة المحمود's real data.

Root cause: `InventoryValuationService.receive_stock`'s moving-average
recompute only ran `if new_total_qty > 0`. Whenever a product was oversold
into negative stock (FR-INV-007's `allow_negative=True`, exercised today
only by Vendor Debit Note restock) and a later receipt still left it
zero-or-negative, that receipt's quantity updated `qty_on_hand` correctly
but its VALUE was silently dropped from `moving_avg_cost` forever --
understating Inventory Valuation against the GL, which always posts a
receipt's true value regardless of the resulting quantity. The fix changes
the guard to `!= 0`, which preserves the algebraic identity
`new_total_qty * new_avg == old_qty*old_avg + qty*unit_cost` for any sign
of new_total_qty -- i.e. `qty_on_hand * moving_avg_cost` always conserves
the cumulative net value of every receipt, oversold or not.

These tests exercise the real business flow that produces a negative
position (a Vendor Debit Note returning more than is currently on hand --
the only `allow_negative=True` call site in the codebase, confirmed by a
prior investigation), not a synthetic direct-issue call.
"""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client, label="NegStock"):
    payload = {
        "tenant_legal_name": f"{label} Holding",
        "company_legal_name": f"{label} Trading Co.",
        "company_legal_name_ar": f"{label} Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": f"{label} Admin",
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


async def _setup_oversold_position(client, headers) -> dict:
    """Receives 100 units @ 20.00 via a real procure-to-pay bill, zeroes
    on-hand via a cycle count (system_qty is snapshotted at the count's
    creation, still 100, so counting 0 issues exactly 100 -- a normal,
    non-negative reduction), then issues a debit note against the bill's
    FULL original qty (100 units) -- with nothing left on hand, this
    oversells by 100, driving the position to -100 through the only
    allow_negative=True path in the codebase. Returns everything needed
    to receive more stock afterward and to independently compute the
    expected conserved value (old_avg stays 20.00 throughout: issues
    never touch moving_avg_cost, only receipts do)."""
    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Negative Stock Vendor", "is_vendor": True}
    )
    vendor_id = vendor_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Oversell Widget", "sales_price": "50.00"},
    )
    product_id = product_resp.json()["id"]
    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True}
    )
    location_id = wh_resp.json()["default_location"]["id"]

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [
                {"product_id": product_id, "qty": "100", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}
            ],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_line_id = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()["lines"][0]["id"]

    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "100"}]},
    )
    # 100 units on hand @ moving_avg_cost=20.00 at this point.

    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "100", "unit_price": "20.00"}]},
    )
    bill_id = bill_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)

    # Count the physical stock down to 0 (a legitimate reduction, well
    # within bounds -- not the allow_negative path) before the debit note.
    cc_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": wh_resp.json()["warehouse"]["id"],
            "scheduled_date": "2026-05-02",
            "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "0"}],
        },
    )
    cycle_count_id = cc_resp.json()["cycle_count"]["id"]
    await client.post(f"/api/v1/inventory/cycle-counts/{cycle_count_id}:approve", headers=headers)

    # Debit note always reverses the bill's FULL original qty (100) --
    # only 0 is on hand, so this oversells by 90 via allow_negative=True.
    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "Full return, oversold on purpose to test negative-stock valuation"},
    )
    assert debit_resp.status_code == 201, debit_resp.text

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    quant = next(q for q in quants if q["product_id"] == product_id)
    assert quant["qty_on_hand"] == "-100.000000"

    return {"headers": headers, "product_id": product_id, "location_id": location_id}


async def test_receipt_while_still_negative_contributes_its_value(client):
    """The exact bug found live: a receipt that arrives while the position
    is still negative afterward must still add its value to
    moving_avg_cost, not just its quantity to qty_on_hand."""
    _, headers = await _bootstrap_and_login(client, "NegReceipt")
    env = await _setup_oversold_position(client, headers)

    # -100 + 50 = -50: still negative after this receipt -- exactly the
    # case the old `if new_total_qty > 0` guard skipped entirely.
    receive_resp = await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": env["product_id"], "location_id": env["location_id"], "qty": "50", "unit_cost": "30.00"},
    )
    assert receive_resp.status_code == 201, receive_resp.text

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    quant = next(q for q in quants if q["product_id"] == env["product_id"])
    assert quant["qty_on_hand"] == "-50.000000"

    # Conservation law: new_total_qty * new_avg == old_qty*old_avg + qty*unit_cost.
    # old_qty=-100, old_avg=20.00 (untouched by the debit note, which never
    # rewrites moving_avg_cost) -> old value = -2000.00.
    # This receipt adds 50 * 30.00 = 1500.00.
    # Expected new value = -2000.00 + 1500.00 = -500.00 -> new_avg = -500/-50 = 10.00.
    expected_avg = Decimal("10.000000")
    assert Decimal(quant["moving_avg_cost"]) == expected_avg, (
        f"expected {expected_avg} (value-conserving), got {quant['moving_avg_cost']} "
        "-- the old bug would leave this at the stale pre-debit-note average (20.00), "
        "silently dropping this receipt's 1500.00 of value"
    )


async def test_valuation_conserves_net_value_through_full_negative_excursion(client):
    """Broader proof: after oversell -> another receipt while still
    negative -> a final receipt that returns the position to positive,
    qty_on_hand * moving_avg_cost must equal the exact sum of every
    signed transaction value that actually happened -- the same identity
    the GL itself is built from."""
    _, headers = await _bootstrap_and_login(client, "NegConserve")
    env = await _setup_oversold_position(client, headers)
    # After setup: qty=-100, old_avg stays 20.00 (untouched by any issue,
    # including the debit note) -> value = -2000.00.

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": env["product_id"], "location_id": env["location_id"], "qty": "60", "unit_cost": "25.00"},
    )
    # -100 + 60 = -40 (still negative). Value: -2000 + 60*25 = -2000+1500 = -500.

    receive3 = await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": env["product_id"], "location_id": env["location_id"], "qty": "100", "unit_cost": "10.00"},
    )
    assert receive3.status_code == 201
    # -40 + 100 = 60 (now positive). Value: -500 + 100*10 = -500+1000 = 500.
    # Final avg = 500 / 60 = 8.333333... (repeating -> 6dp).

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    quant = next(q for q in quants if q["product_id"] == env["product_id"])
    assert quant["qty_on_hand"] == "60.000000"
    assert quant["moving_avg_cost"] == "8.333333"


async def test_moving_avg_cost_stores_six_decimal_places(client):
    """Schema/precision confirmation: the column now carries six decimal
    places (was four), and a blend that would round differently at 4dp
    vs 6dp reflects the finer precision -- the fix for the compounding-
    rounding half of the original finding."""
    _, headers = await _bootstrap_and_login(client, "SixDp")
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Precision Widget", "sales_price": "10.00"},
    )
    product_id = product_resp.json()["id"]
    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True}
    )
    location_id = wh_resp.json()["default_location"]["id"]

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "1", "unit_cost": "10.00"},
    )
    # (1*10.00 + 2*11.00) / 3 = 32/3 = 10.6666... -- a genuine repeating
    # decimal. At the old NUMERIC(18,4)/4dp precision this would store as
    # 10.6667; at the new NUMERIC(18,6)/6dp precision it stores as
    # 10.666667 -- proof the finer precision is actually in effect, not
    # just declared.
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "2", "unit_cost": "11.00"},
    )
    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    quant = next(q for q in quants if q["product_id"] == product_id)
    assert quant["qty_on_hand"] == "3.000000"
    assert quant["moving_avg_cost"] == "10.666667"
