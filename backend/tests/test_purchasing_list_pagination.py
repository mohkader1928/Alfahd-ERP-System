"""Integration smoke test for server-side pagination/filtering on the
Purchase Orders and Vendor Bills lists (Product Owner audit, same pattern
established for Sales Invoices): real LIMIT/OFFSET, a correct total, and
status/date/partner filters that actually narrow the server-side query,
instead of the list screen loading every row unbounded.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Purch Pagination Holding",
        "company_legal_name": "Purch Pagination Trading Co.",
        "company_legal_name_ar": "Purch Pagination Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Purch Pagination Admin",
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


async def _create_po(client, headers, *, order_date: str = "2026-06-01"):
    vendor = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Pagination Vendor", "is_vendor": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"PPAGE-{unique_vat()[:8]}", "name": "Pagination Product", "cost_price": "10.00"},
    )
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor.json()["id"],
            "order_date": order_date,
            "lines": [{"product_id": product.json()["id"], "qty": "1", "unit_price": "10.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert po_resp.status_code == 201
    return po_resp.json(), vendor.json()["id"]


async def test_purchase_orders_pagination_returns_distinct_pages(client):
    _, headers = await _bootstrap_and_login(client)
    orders = [(await _create_po(client, headers))[0] for _ in range(5)]
    order_ids = {o["id"] for o in orders}

    page1 = (await client.get("/api/v1/purchasing/orders", headers=headers, params={"page": 1, "page_size": 2})).json()
    assert page1["total"] == 5
    page2 = (await client.get("/api/v1/purchasing/orders", headers=headers, params={"page": 2, "page_size": 2})).json()
    page3 = (await client.get("/api/v1/purchasing/orders", headers=headers, params={"page": 3, "page_size": 2})).json()

    seen = {o["id"] for o in page1["items"] + page2["items"] + page3["items"]}
    assert seen == order_ids


async def test_purchase_orders_status_and_date_filters(client):
    _, headers = await _bootstrap_and_login(client)
    order, _ = await _create_po(client, headers, order_date="2026-06-01")

    draft_only = (await client.get("/api/v1/purchasing/orders", headers=headers, params={"status": "draft"})).json()
    assert any(o["id"] == order["id"] for o in draft_only["items"])

    confirmed_only = (
        await client.get("/api/v1/purchasing/orders", headers=headers, params={"status": "confirmed"})
    ).json()
    assert not any(o["id"] == order["id"] for o in confirmed_only["items"])

    out_of_range = (
        await client.get(
            "/api/v1/purchasing/orders",
            headers=headers,
            params={"date_from": "2020-01-01", "date_to": "2020-12-31"},
        )
    ).json()
    assert out_of_range["total"] == 0


async def test_vendor_bills_pagination_and_partner_filter(client):
    _, headers = await _bootstrap_and_login(client)

    async def _issue_bill():
        order, vendor_id = await _create_po(client, headers)
        await client.post(f"/api/v1/purchasing/orders/{order['id']}:confirm", headers=headers)
        po_line_id = (await client.get(f"/api/v1/purchasing/orders/{order['id']}", headers=headers)).json()["lines"][0]["id"]
        bill_resp = await client.post(
            f"/api/v1/purchasing/orders/{order['id']}/vendor-bills",
            headers=headers,
            json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "1", "unit_price": "10.00"}]},
        )
        assert bill_resp.status_code == 201
        return bill_resp.json(), vendor_id

    bills_and_vendors = [await _issue_bill() for _ in range(3)]
    all_bill_ids = {b["id"] for b, _ in bills_and_vendors}

    page1 = (await client.get("/api/v1/purchasing/vendor-bills", headers=headers, params={"page": 1, "page_size": 2})).json()
    assert page1["total"] == 3
    page2 = (await client.get("/api/v1/purchasing/vendor-bills", headers=headers, params={"page": 2, "page_size": 2})).json()
    seen = {b["id"] for b in page1["items"] + page2["items"]}
    assert seen == all_bill_ids

    target_bill, target_vendor_id = bills_and_vendors[0]
    filtered = (
        await client.get("/api/v1/purchasing/vendor-bills", headers=headers, params={"partner_id": target_vendor_id})
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == target_bill["id"]


async def test_purchasing_lists_require_permission(client):
    orders_resp = await client.get("/api/v1/purchasing/orders")
    assert orders_resp.status_code == 401
    bills_resp = await client.get("/api/v1/purchasing/vendor-bills")
    assert bills_resp.status_code == 401
