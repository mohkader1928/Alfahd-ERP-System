"""Integration smoke test for the Purchase Order Approval Workflow +
Notifications (Product Owner directive, 2026-08-07 — full-system audit
found this explicitly flagged, not silently missing, in
purchasing/application/services.py's own docstring: FR-CORE-052 was
deferred and never built).

Exercises: a PO under the company's approval threshold still auto-confirms
(no regression to existing behavior); a PO over the threshold routes to
`pending_approval` and notifies every user holding
`purchasing.order.approve` except the PO's own creator; approving confirms
the order and notifies the creator back; rejecting sends it back to draft
with a reason and notifies the creator.
"""


from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Approval Test Holding",
        "company_legal_name": "Approval Test Trading Co.",
        "company_legal_name_ar": "Approval Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Approval Test Admin",
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


async def _set_threshold(client, admin_headers, company_id, threshold: str):
    company = (await client.get(f"/api/v1/identity/companies/{company_id}", headers=admin_headers)).json()
    resp = await client.patch(
        f"/api/v1/identity/companies/{company_id}",
        headers=admin_headers,
        json={
            "legal_name": company["legal_name"],
            "legal_name_ar": company["legal_name_ar"],
            "vat_number": company["vat_number"],
            "cr_number": company["cr_number"],
            "po_approval_threshold": threshold,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["po_approval_threshold"] == threshold


async def _create_approver_user(client, admin_headers, company_id):
    """A second user holding ONLY purchasing.order.approve — proves
    notification targeting is permission-driven, not "every Admin"."""
    role_resp = await client.post(
        "/api/v1/identity/roles", headers=admin_headers, json={"name": "PO Approver"}
    )
    assert role_resp.status_code == 201
    role_id = role_resp.json()["id"]
    perm_resp = await client.put(
        f"/api/v1/identity/roles/{role_id}/permissions",
        headers=admin_headers,
        json={"permission_codes": ["purchasing.order.approve", "purchasing.order.view"]},
    )
    assert perm_resp.status_code == 200

    email = unique_email()
    password = "Str0ng!Passw0rd"
    create_resp = await client.post(
        "/api/v1/identity/users",
        headers=admin_headers,
        json={"email": email, "full_name": "PO Approver", "password": password, "company_id": company_id},
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]
    assign_resp = await client.post(
        f"/api/v1/identity/users/{user_id}/roles", headers=admin_headers, json={"role_id": role_id}
    )
    assert assign_resp.status_code == 204

    login_resp = await client.post("/api/v1/identity/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]
    approver_headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return user_id, approver_headers


async def _create_and_confirm_po(client, headers, *, unit_price: str):
    vendor = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Approval Vendor", "is_vendor": True}
    )
    vendor_id = vendor.json()["id"]
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"APPR-{unique_vat()[:8]}", "name": "Approval Product", "cost_price": unit_price},
    )
    product_id = product.json()["id"]
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-08-01",
            "lines": [
                {"product_id": product_id, "qty": "1", "unit_price": unit_price, "tax_rate_id": TAX_RATE_PLACEHOLDER}
            ],
        },
    )
    assert po_resp.status_code == 201, po_resp.text
    order_id = po_resp.json()["id"]
    confirm_resp = await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    assert confirm_resp.status_code == 200, confirm_resp.text
    return confirm_resp.json()


async def test_po_under_threshold_auto_confirms(client):
    """No regression: a company with a threshold set still auto-confirms a
    PO that doesn't exceed it — the gate only engages above the line."""
    company_id, headers = await _bootstrap_and_login(client)
    await _set_threshold(client, headers, company_id, "5000.0000")

    order = await _create_and_confirm_po(client, headers, unit_price="100.00")
    assert order["status"] == "confirmed"
    assert order["approval_status"] == "not_required"


async def test_po_over_threshold_requires_approval_and_notifies(client):
    company_id, headers = await _bootstrap_and_login(client)
    await _set_threshold(client, headers, company_id, "1000.0000")
    approver_id, approver_headers = await _create_approver_user(client, headers, company_id)

    order = await _create_and_confirm_po(client, headers, unit_price="5000.00")
    assert order["status"] == "pending_approval"
    assert order["approval_status"] == "pending"

    # The approver was notified...
    approver_notifs = (await client.get("/api/v1/notifications", headers=approver_headers)).json()
    assert any(n["type"] == "po_approval_requested" and n["entity_id"] == order["id"] for n in approver_notifs)

    # ...but the creator (admin) was not notified about their own submission,
    # even though Admin also holds purchasing.order.approve.
    admin_notifs = (await client.get("/api/v1/notifications", headers=headers)).json()
    assert not any(n["type"] == "po_approval_requested" for n in admin_notifs)

    unread = (await client.get("/api/v1/notifications/unread-count", headers=approver_headers)).json()
    assert unread["count"] >= 1


async def test_approve_confirms_order_and_notifies_creator(client):
    company_id, headers = await _bootstrap_and_login(client)
    await _set_threshold(client, headers, company_id, "1000.0000")
    _, approver_headers = await _create_approver_user(client, headers, company_id)

    order = await _create_and_confirm_po(client, headers, unit_price="5000.00")
    order_id = order["id"]

    approve_resp = await client.post(f"/api/v1/purchasing/orders/{order_id}:approve", headers=approver_headers)
    assert approve_resp.status_code == 200, approve_resp.text
    approved = approve_resp.json()
    assert approved["status"] == "confirmed"
    assert approved["approval_status"] == "approved"
    assert approved["approved_by"] is not None

    admin_notifs = (await client.get("/api/v1/notifications", headers=headers)).json()
    assert any(n["type"] == "po_approved" and n["entity_id"] == order_id for n in admin_notifs)


async def test_reject_returns_to_draft_with_reason_and_notifies_creator(client):
    company_id, headers = await _bootstrap_and_login(client)
    await _set_threshold(client, headers, company_id, "1000.0000")
    _, approver_headers = await _create_approver_user(client, headers, company_id)

    order = await _create_and_confirm_po(client, headers, unit_price="5000.00")
    order_id = order["id"]

    reject_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}:reject",
        headers=approver_headers,
        json={"reason": "Vendor price is above market rate"},
    )
    assert reject_resp.status_code == 200, reject_resp.text
    rejected = reject_resp.json()
    assert rejected["status"] == "draft"
    assert rejected["approval_status"] == "rejected"
    assert rejected["rejection_reason"] == "Vendor price is above market rate"

    admin_notifs = (await client.get("/api/v1/notifications", headers=headers)).json()
    match = next(n for n in admin_notifs if n["type"] == "po_rejected" and n["entity_id"] == order_id)
    assert "Vendor price is above market rate" in match["body"]

    # A rejected PO is a draft again — it can be edited and re-confirmed,
    # not stuck in a dead state.
    reconfirm_resp = await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    assert reconfirm_resp.status_code == 200
    assert reconfirm_resp.json()["status"] == "pending_approval"


async def test_notification_requires_permission_not_just_admin_role(client):
    """A user who does NOT hold purchasing.order.approve must not be able
    to approve, even with knowledge of the order id — the permission
    system, not just knowing the notification exists, is the real gate."""
    company_id, headers = await _bootstrap_and_login(client)
    await _set_threshold(client, headers, company_id, "1000.0000")

    order = await _create_and_confirm_po(client, headers, unit_price="5000.00")
    order_id = order["id"]

    role_resp = await client.post("/api/v1/identity/roles", headers=headers, json={"name": "No Approve"})
    role_id = role_resp.json()["id"]
    await client.put(
        f"/api/v1/identity/roles/{role_id}/permissions",
        headers=headers,
        json={"permission_codes": ["purchasing.order.view"]},
    )
    email = unique_email()
    password = "Str0ng!Passw0rd"
    create_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": email, "full_name": "No Approve User", "password": password, "company_id": company_id},
    )
    user_id = create_resp.json()["id"]
    await client.post(f"/api/v1/identity/users/{user_id}/roles", headers=headers, json={"role_id": role_id})
    login_resp = await client.post("/api/v1/identity/auth/login", json={"email": email, "password": password})
    no_approve_headers = {
        "Authorization": f"Bearer {login_resp.json()['access_token']}",
        "X-Company-Id": company_id,
    }

    resp = await client.post(f"/api/v1/purchasing/orders/{order_id}:approve", headers=no_approve_headers)
    assert resp.status_code == 403
