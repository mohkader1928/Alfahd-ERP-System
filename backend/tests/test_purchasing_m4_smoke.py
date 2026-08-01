"""Integration smoke test for Backend M4 — Purchasing.

Exercises UC-PUR-01 end to end: PO -> confirm -> Goods Receipt (increases
stock + accrues GRNI liability) -> Vendor Bill -> 3-Way Match -> approve
(reverses GRNI into Accounts Payable), per FR-PUR-001..005.
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Pur Test Holding",
        "company_legal_name": "Pur Test Trading Co.",
        "company_legal_name_ar": "Pur Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Pur Test Admin",
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


async def _create_vendor(client, headers) -> str:
    resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Steel Supplier LLC", "is_vendor": True}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_product(client, headers) -> str:
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Steel Rod", "sales_price": "50.00"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_warehouse(client, headers):
    resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "PO Warehouse", "is_default": True}
    )
    assert resp.status_code == 201
    return resp.json()


TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def test_full_procure_to_pay_cycle_matched(client):
    _, headers = await _bootstrap_and_login(client)
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
    await _create_warehouse(client, headers)

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "100", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert po_resp.status_code == 201
    order_id = po_resp.json()["id"]
    assert po_resp.json()["status"] == "draft"

    confirm_resp = await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "confirmed"

    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]

    receipt_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "100"}]},
    )
    assert receipt_resp.status_code == 201

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    assert quants[0]["qty_on_hand"] == "100.000000"

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    assert rows["1300"]["total_debit"] == "2000.0000"  # Inventory: 100 * 20.00
    assert rows["2300"]["total_credit"] == "2000.0000"  # GRNI accrual

    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "INV-9001", "lines": [{"purchase_order_line_id": po_line_id, "qty": "100", "unit_price": "20.00"}]},
    )
    assert bill_resp.status_code == 201
    bill = bill_resp.json()
    assert bill["status"] == "matched"
    bill_id = bill["id"]

    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "posted"

    trial_balance2 = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows2 = {row["account_code"]: row for row in trial_balance2.json()}
    # GRNI: debited 2000 (bill approval, ex-tax) + credited 2000 (receipt accrual) = nets to zero
    assert rows2["2300"]["total_debit"] == rows2["2300"]["total_credit"] == "2000.0000"
    assert rows2["2100"]["total_credit"] == "2300.0000"  # Accounts Payable: full tax-inclusive amount owed
    assert rows2["2200"]["total_debit"] == "300.0000"  # Input VAT on the bill


async def test_vendor_bill_price_mismatch_blocks_approval(client):
    _, headers = await _bootstrap_and_login(client)
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
    await _create_warehouse(client, headers)

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "10", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)

    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]

    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "10"}]},
    )

    # Bill at a different price than the PO — should fail 3-way match.
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "10", "unit_price": "25.00"}]},
    )
    assert bill_resp.status_code == 201
    bill = bill_resp.json()
    assert bill["status"] == "mismatched"
    assert "!= PO price" in bill["mismatch_reasons"]

    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill['id']}:approve", headers=headers)
    assert approve_resp.status_code == 409


async def test_bill_quantity_exceeding_received_qty_mismatches(client):
    _, headers = await _bootstrap_and_login(client)
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
    await _create_warehouse(client, headers)

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "10", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)

    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]

    # Only receive half.
    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "5"}]},
    )

    # But bill for the full quantity.
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "10", "unit_price": "20.00"}]},
    )
    assert bill_resp.status_code == 201
    assert bill_resp.json()["status"] == "mismatched"


async def test_receiving_more_than_ordered_qty_rejected(client):
    _, headers = await _bootstrap_and_login(client)
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
    await _create_warehouse(client, headers)

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "10", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)

    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]

    over_receipt_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "15"}]},
    )
    assert over_receipt_resp.status_code == 422


async def test_purchasing_endpoints_require_permission(client):
    resp = await client.post("/api/v1/purchasing/orders", json={})
    assert resp.status_code == 401


async def test_list_purchase_orders_and_vendor_bills(client):
    _, headers = await _bootstrap_and_login(client)
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
    await _create_warehouse(client, headers)

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "5", "unit_price": "10.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]

    list_resp = await client.get("/api/v1/purchasing/orders", headers=headers)
    assert list_resp.status_code == 200
    assert any(o["id"] == order_id for o in list_resp.json())

    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_line_id = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()["lines"][0]["id"]
    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "5"}]},
    )
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "5", "unit_price": "10.00"}]},
    )
    bill_id = bill_resp.json()["id"]

    bills_resp = await client.get("/api/v1/purchasing/vendor-bills", headers=headers)
    assert bills_resp.status_code == 200
    assert any(b["id"] == bill_id for b in bills_resp.json())


async def test_purchase_orders_not_visible_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client)
    vendor_id = await _create_vendor(client, headers_a)
    product_id = await _create_product(client, headers_a)
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers_a,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "5.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]

    _, headers_b = await _bootstrap_and_login(client)
    list_resp = await client.get("/api/v1/purchasing/orders", headers=headers_b)
    assert all(o["id"] != order_id for o in list_resp.json())
    detail_resp = await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers_b)
    assert detail_resp.status_code == 404
