"""Unified Address Book / Partner & Contacts bundle.

Exercises the real HTTP layer per this repo's testing convention (see
test_entity_media_foundation.py): Partner as the single master entity for
Customer/Vendor/Employee/Contact roles, Contact-as-Partner via
parent_partner_id, multi-address CRUD, archive/restore, and company
isolation/permission enforcement for all of the above.
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Address Book Test Holding",
        "company_legal_name": "Address Book Test Co.",
        "company_legal_name_ar": "شركة اختبار دفتر العناوين",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Address Book Test Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    company_id = resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return headers, company_id


async def _no_role_headers(client, headers, company_id):
    email = unique_email()
    await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": email, "full_name": "No Role User", "password": "Str0ng!Passw0rd", "company_id": company_id},
    )
    login = await client.post("/api/v1/identity/auth/login", json={"email": email, "password": "Str0ng!Passw0rd"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}


async def test_partner_can_be_created_with_no_role_flags(client):
    """A pure contact person or an undecided company/individual is now a
    legitimate state — the old "must be customer or vendor" rule is gone."""
    headers, _ = await _bootstrap_and_login(client)
    resp = await client.post("/api/v1/identity/partners", headers=headers, json={"name": "Undecided Partner"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_customer"] is False
    assert body["is_vendor"] is False
    assert body["is_employee"] is False


async def test_partner_can_be_customer_vendor_and_employee_simultaneously(client):
    headers, _ = await _bootstrap_and_login(client)
    resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "Triple Role Partner", "is_customer": True, "is_vendor": True, "is_employee": True},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_customer"] and body["is_vendor"] and body["is_employee"]

    # Appears in each filtered view.
    for flag in ("customers_only", "vendors_only", "employees_only"):
        listing = await client.get(f"/api/v1/identity/partners?{flag}=true", headers=headers)
        ids = [p["id"] for p in listing.json()]
        assert body["id"] in ids

    # No duplicate created — exactly one partner with this name exists.
    all_partners = await client.get("/api/v1/identity/partners", headers=headers)
    matches = [p for p in all_partners.json() if p["name"] == "Triple Role Partner"]
    assert len(matches) == 1


async def test_contact_person_is_a_real_partner_linked_via_parent(client):
    """Condition 2: a Contact Person is a full Partner row from the start
    (is_company=false, parent_partner_id set), not a separate lightweight
    table — so it can gain Customer/Vendor/Employee later on the same row,
    with zero migration of identity data."""
    headers, _ = await _bootstrap_and_login(client)

    company_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Contact Co ABC", "is_customer": True}
    )
    company_id_partner = company_resp.json()["id"]

    contact_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={
            "name": "Ahmed Mohammed",
            "is_company": False,
            "parent_partner_id": company_id_partner,
            "job_title": "Purchasing Manager",
            "is_primary_contact": True,
            "email": "ahmed@contactco.example",
        },
    )
    assert contact_resp.status_code == 201
    contact = contact_resp.json()
    assert contact["is_company"] is False
    assert contact["parent_partner_id"] == company_id_partner
    assert contact["job_title"] == "Purchasing Manager"

    # Appears when listing this company's contacts.
    contacts = await client.get(
        f"/api/v1/identity/partners?parent_partner_id={company_id_partner}", headers=headers
    )
    assert [c["id"] for c in contacts.json()] == [contact["id"]]

    # "Promotion": Ahmed becomes an Employee, on the SAME row/id — no new
    # partner created, no id change.
    promote_resp = await client.patch(
        f"/api/v1/identity/partners/{contact['id']}",
        headers=headers,
        json={
            "name": "Ahmed Mohammed",
            "is_company": False,
            "is_employee": True,
            "job_title": "Purchasing Manager",
            "is_primary_contact": True,
            "email": "ahmed@contactco.example",
        },
    )
    assert promote_resp.status_code == 200
    promoted = promote_resp.json()
    assert promoted["id"] == contact["id"]
    assert promoted["is_employee"] is True

    employees = await client.get("/api/v1/identity/partners?employees_only=true", headers=headers)
    assert promoted["id"] in [p["id"] for p in employees.json()]


async def test_parent_partner_must_exist_in_same_company(client):
    headers_a, _ = await _bootstrap_and_login(client)
    headers_b, _ = await _bootstrap_and_login(client)

    other_company_partner = await client.post(
        "/api/v1/identity/partners", headers=headers_b, json={"name": "Company B Partner"}
    )
    other_id = other_company_partner.json()["id"]

    resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers_a,
        json={"name": "Cross Company Contact", "is_company": False, "parent_partner_id": other_id},
    )
    assert resp.status_code == 422


async def test_partner_address_crud_and_default_enforcement(client):
    headers, _ = await _bootstrap_and_login(client)
    partner = await client.post("/api/v1/identity/partners", headers=headers, json={"name": "Address Test Partner"})
    partner_id = partner.json()["id"]

    billing_1 = await client.post(
        f"/api/v1/identity/partners/{partner_id}/addresses",
        headers=headers,
        json={"type": "billing", "is_default": True, "city": "Riyadh"},
    )
    assert billing_1.status_code == 201
    assert billing_1.json()["is_default"] is True

    billing_2 = await client.post(
        f"/api/v1/identity/partners/{partner_id}/addresses",
        headers=headers,
        json={"type": "billing", "is_default": True, "city": "Jeddah"},
    )
    assert billing_2.status_code == 201

    shipping = await client.post(
        f"/api/v1/identity/partners/{partner_id}/addresses",
        headers=headers,
        json={"type": "shipping", "is_default": True, "city": "Dammam"},
    )
    assert shipping.status_code == 201

    listing = (await client.get(f"/api/v1/identity/partners/{partner_id}/addresses", headers=headers)).json()
    assert len(listing) == 3
    billing_rows = [a for a in listing if a["type"] == "billing"]
    assert sum(1 for a in billing_rows if a["is_default"]) == 1
    default_billing = next(a for a in billing_rows if a["is_default"])
    assert default_billing["city"] == "Jeddah"
    shipping_rows = [a for a in listing if a["type"] == "shipping"]
    assert shipping_rows[0]["is_default"] is True

    update_resp = await client.patch(
        f"/api/v1/identity/partners/{partner_id}/addresses/{billing_1.json()['id']}",
        headers=headers,
        json={"type": "other", "is_default": False, "city": "Mecca"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["type"] == "other"
    assert update_resp.json()["city"] == "Mecca"

    delete_resp = await client.delete(
        f"/api/v1/identity/partners/{partner_id}/addresses/{shipping.json()['id']}", headers=headers
    )
    assert delete_resp.status_code == 204
    remaining = (await client.get(f"/api/v1/identity/partners/{partner_id}/addresses", headers=headers)).json()
    assert len(remaining) == 2


async def test_partner_address_rejects_cross_company_access(client):
    headers_a, _ = await _bootstrap_and_login(client)
    headers_b, _ = await _bootstrap_and_login(client)

    partner_a = await client.post("/api/v1/identity/partners", headers=headers_a, json={"name": "Company A Partner"})
    partner_a_id = partner_a.json()["id"]
    address_a = await client.post(
        f"/api/v1/identity/partners/{partner_a_id}/addresses",
        headers=headers_a,
        json={"type": "billing", "city": "Riyadh"},
    )
    address_a_id = address_a.json()["id"]

    read_resp = await client.get(f"/api/v1/identity/partners/{partner_a_id}/addresses", headers=headers_b)
    assert read_resp.status_code == 404

    update_resp = await client.patch(
        f"/api/v1/identity/partners/{partner_a_id}/addresses/{address_a_id}",
        headers=headers_b,
        json={"type": "billing", "city": "Hacked"},
    )
    assert update_resp.status_code == 404

    delete_resp = await client.delete(
        f"/api/v1/identity/partners/{partner_a_id}/addresses/{address_a_id}", headers=headers_b
    )
    assert delete_resp.status_code == 404


async def test_partner_archive_and_restore(client):
    headers, _ = await _bootstrap_and_login(client)
    partner = await client.post("/api/v1/identity/partners", headers=headers, json={"name": "Archivable Partner"})
    partner_id = partner.json()["id"]

    archive_resp = await client.post(f"/api/v1/identity/partners/{partner_id}/archive", headers=headers)
    assert archive_resp.status_code == 200
    assert archive_resp.json()["is_active"] is False

    active_listing = await client.get("/api/v1/identity/partners", headers=headers)
    assert partner_id not in [p["id"] for p in active_listing.json()]

    archived_listing = await client.get("/api/v1/identity/partners?include_archived=true", headers=headers)
    assert partner_id in [p["id"] for p in archived_listing.json()]

    get_resp = await client.get(f"/api/v1/identity/partners/{partner_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False

    restore_resp = await client.post(f"/api/v1/identity/partners/{partner_id}/restore", headers=headers)
    assert restore_resp.status_code == 200
    assert restore_resp.json()["is_active"] is True

    active_listing_after = await client.get("/api/v1/identity/partners", headers=headers)
    assert partner_id in [p["id"] for p in active_listing_after.json()]


async def test_partner_archive_rejects_cross_company(client):
    headers_a, _ = await _bootstrap_and_login(client)
    headers_b, _ = await _bootstrap_and_login(client)
    partner = await client.post("/api/v1/identity/partners", headers=headers_a, json={"name": "Company A Partner"})
    partner_id = partner.json()["id"]

    resp = await client.post(f"/api/v1/identity/partners/{partner_id}/archive", headers=headers_b)
    assert resp.status_code == 404


async def test_address_book_endpoints_require_permission(client):
    """A user with no role assignment has zero permissions in that company —
    real RBAC data, same pattern as test_entity_media_foundation.py."""
    headers, company_id = await _bootstrap_and_login(client)
    no_role_headers = await _no_role_headers(client, headers, company_id)

    partner = await client.post("/api/v1/identity/partners", headers=headers, json={"name": "Perm Test Partner"})
    partner_id = partner.json()["id"]

    assert (await client.post("/api/v1/identity/partners", headers=no_role_headers, json={"name": "X"})).status_code == 403
    assert (
        await client.post(
            f"/api/v1/identity/partners/{partner_id}/addresses",
            headers=no_role_headers,
            json={"type": "billing"},
        )
    ).status_code == 403
    assert (await client.post(f"/api/v1/identity/partners/{partner_id}/archive", headers=no_role_headers)).status_code == 403
    assert (await client.get("/api/v1/identity/partners", headers=no_role_headers)).status_code == 403
