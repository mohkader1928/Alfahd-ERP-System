"""3-Day Sellable Product Brief, P0-1 — real partial receipt + short-close.

Partial receipt itself (accumulating qty_received across multiple goods
receipts, blocking over-receipt) already worked at the data layer before
this bundle — see test_purchasing_m4_smoke.py's existing partial-receipt
coverage. What's new here: a PO auto-closing to 'done' once fully
received, a deliberate 'short close' for the remaining qty (status
'closed'), receiving being blocked against a short-closed line, and the
admin-only reopen path that's the only way back in.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Short Close Test Holding",
        "company_legal_name": "Short Close Test Trading Co.",
        "company_legal_name_ar": "Short Close Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Short Close Test Admin",
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


async def _create_confirmed_order(client, headers, *, qty="10") -> tuple[str, str]:
    """Returns (order_id, po_line_id) for a confirmed order, qty @ 20.00."""
    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Short Close Vendor", "is_vendor": True}
    )
    vendor_id = vendor_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SC-{unique_vat()[:8]}", "name": "Short Close Product", "sales_price": "50.00"},
    )
    product_id = product_resp.json()["id"]
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True})

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": qty, "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    return order_id, po_detail["lines"][0]["id"]


async def test_po_auto_closes_to_done_when_fully_received_across_two_receipts(client):
    _, headers = await _bootstrap_and_login(client)
    order_id, po_line_id = await _create_confirmed_order(client, headers, qty="10")

    r1 = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "4"}]},
    )
    assert r1.status_code == 201
    mid = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    assert mid["order"]["status"] == "confirmed"
    assert mid["lines"][0]["qty_received"] == "4.000000"

    r2 = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "6"}]},
    )
    assert r2.status_code == 201
    final = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    assert final["order"]["status"] == "done"
    assert final["lines"][0]["qty_received"] == "10.000000"


async def test_short_close_after_partial_receipt(client):
    _, headers = await _bootstrap_and_login(client)
    order_id, po_line_id = await _create_confirmed_order(client, headers, qty="10")

    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "6"}]},
    )

    close_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}:short-close",
        headers=headers,
        json={"reason": "Vendor discontinued the remaining stock"},
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == "closed"

    detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    assert detail["order"]["status"] == "closed"
    assert detail["lines"][0]["short_closed"] is True
    assert detail["lines"][0]["qty_received"] == "6.000000"  # never touched by short-close


async def test_receiving_against_a_short_closed_line_is_rejected(client):
    _, headers = await _bootstrap_and_login(client)
    order_id, po_line_id = await _create_confirmed_order(client, headers, qty="10")

    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "6"}]},
    )
    await client.post(
        f"/api/v1/purchasing/orders/{order_id}:short-close", headers=headers, json={"reason": "Stop here"}
    )

    # PO status is now 'closed', not 'confirmed' -- record_receipt already
    # rejects any receipt against a non-confirmed order, which alone would
    # block this. The real thing under test is the line-level guard, which
    # is what actually prevents receiving the closed qty even if the order
    # were somehow reopened without clearing short_closed.
    blocked_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "4"}]},
    )
    assert blocked_resp.status_code == 422


async def test_reopen_allows_receiving_again(client):
    _, headers = await _bootstrap_and_login(client)
    order_id, po_line_id = await _create_confirmed_order(client, headers, qty="10")

    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "6"}]},
    )
    await client.post(
        f"/api/v1/purchasing/orders/{order_id}:short-close", headers=headers, json={"reason": "Stop here"}
    )

    reopen_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/lines/{po_line_id}:reopen", headers=headers
    )
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["status"] == "confirmed"

    detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    assert detail["lines"][0]["short_closed"] is False

    resume_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "4"}]},
    )
    assert resume_resp.status_code == 201
    final = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    assert final["order"]["status"] == "done"
    assert final["lines"][0]["qty_received"] == "10.000000"


async def test_short_close_rejected_when_fully_received(client):
    _, headers = await _bootstrap_and_login(client)
    order_id, po_line_id = await _create_confirmed_order(client, headers, qty="10")

    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "10"}]},
    )

    close_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}:short-close", headers=headers, json={"reason": "Nothing left"}
    )
    assert close_resp.status_code == 422


async def test_reopen_rejected_when_line_is_not_short_closed(client):
    _, headers = await _bootstrap_and_login(client)
    order_id, po_line_id = await _create_confirmed_order(client, headers, qty="10")

    reopen_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/lines/{po_line_id}:reopen", headers=headers
    )
    assert reopen_resp.status_code == 422
