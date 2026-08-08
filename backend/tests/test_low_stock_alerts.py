"""Low stock / reorder-point alerts — Product Owner audit finding: "what's
below reorder point right now?" is table-stakes in every reference ERP
(SAP B1, Dynamics 365 BC, Odoo) and was entirely absent (no reorder_point
field on the product master, no low-stock query, no alert). Reuses the
existing Notifications module (Approval Workflow bundle) for delivery.
"""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "LowStock Test Holding",
        "company_legal_name": "LowStock Test Trading Co.",
        "company_legal_name_ar": "LowStock Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "LowStock Test Admin",
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


async def test_product_reorder_point_round_trips(client):
    _, headers = await _bootstrap_and_login(client)
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"RP-{unique_vat()[:8]}", "name": "Reorder Widget", "sales_price": "10.00", "reorder_point": "5"},
    )
    assert resp.status_code == 201
    assert Decimal(resp.json()["reorder_point"]) == Decimal("5")

    update_resp = await client.patch(
        f"/api/v1/identity/products/{resp.json()['id']}",
        headers=headers,
        json={"sku": resp.json()["sku"], "name": "Reorder Widget", "sales_price": "10.00", "reorder_point": "8"},
    )
    assert update_resp.status_code == 200
    assert Decimal(update_resp.json()["reorder_point"]) == Decimal("8")


async def test_low_stock_endpoint_lists_only_products_below_threshold(client):
    company_id, headers = await _bootstrap_and_login(client)

    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True}
    )
    location_id = wh_resp.json()["default_location"]["id"]

    low_product = (
        await client.post(
            "/api/v1/identity/products",
            headers=headers,
            json={"sku": f"LOW-{unique_vat()[:8]}", "name": "Low Widget", "sales_price": "10.00", "reorder_point": "20"},
        )
    ).json()
    ok_product = (
        await client.post(
            "/api/v1/identity/products",
            headers=headers,
            json={"sku": f"OK-{unique_vat()[:8]}", "name": "OK Widget", "sales_price": "10.00", "reorder_point": "5"},
        )
    ).json()
    no_threshold_product = (
        await client.post(
            "/api/v1/identity/products",
            headers=headers,
            json={"sku": f"NONE-{unique_vat()[:8]}", "name": "No Threshold Widget", "sales_price": "10.00"},
        )
    ).json()

    # low_product: 10 on hand, reorder_point 20 -> below.
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": low_product["id"], "location_id": location_id, "qty": "10", "unit_cost": "5.00"},
    )
    # ok_product: 50 on hand, reorder_point 5 -> comfortably above.
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": ok_product["id"], "location_id": location_id, "qty": "50", "unit_cost": "5.00"},
    )
    # no_threshold_product: zero stock, but no reorder_point configured -> never a candidate.
    assert no_threshold_product["reorder_point"] is None

    resp = await client.get("/api/v1/inventory/stock/low-stock", headers=headers)
    assert resp.status_code == 200
    rows = {row["product_id"]: row for row in resp.json()}
    assert low_product["id"] in rows
    assert rows[low_product["id"]]["qty_on_hand"] == "10.000000"
    assert rows[low_product["id"]]["shortfall"] == "10.000000"
    assert ok_product["id"] not in rows
    assert no_threshold_product["id"] not in rows


async def test_issuing_stock_below_reorder_point_creates_a_notification(client):
    company_id, headers = await _bootstrap_and_login(client)

    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True}
    )
    location_id = wh_resp.json()["default_location"]["id"]

    product = (
        await client.post(
            "/api/v1/identity/products",
            headers=headers,
            json={"sku": f"CROSS-{unique_vat()[:8]}", "name": "Crossing Widget", "sales_price": "100.00", "reorder_point": "5"},
        )
    ).json()
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product["id"], "location_id": location_id, "qty": "10", "unit_cost": "40.00"},
    )

    partner = (
        await client.post(
            "/api/v1/identity/partners", headers=headers, json={"name": "Crossing Customer", "is_customer": True}
        )
    ).json()
    quote = (
        await client.post(
            "/api/v1/sales/quotations",
            headers=headers,
            json={
                "partner_id": partner["id"],
                "quote_date": "2026-06-01",
                "lines": [
                    {"product_id": product["id"], "qty": "7", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}
                ],
            },
        )
    ).json()
    order = (await client.post(f"/api/v1/sales/quotations/{quote['id']}:confirm", headers=headers)).json()

    # Before invoicing: 10 on hand, reorder_point 5 -> no alert yet.
    notifications_before = (await client.get("/api/v1/notifications", headers=headers)).json()
    assert not any(n["type"] == "low_stock" for n in notifications_before)

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order['id']}:invoice", headers=headers)
    assert invoice_resp.status_code == 201

    # After invoicing 7 units: 10 - 7 = 3 on hand, reorder_point 5 -> crossed below, notified.
    notifications_after = (await client.get("/api/v1/notifications", headers=headers)).json()
    low_stock_notifications = [n for n in notifications_after if n["type"] == "low_stock"]
    assert len(low_stock_notifications) == 1
    assert low_stock_notifications[0]["entity_id"] == product["id"]
