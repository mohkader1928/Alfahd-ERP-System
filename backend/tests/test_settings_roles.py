"""Settings Architecture Foundation milestone — Company Settings + Security
(Roles & Permissions).

Exercises the real operational gap this milestone closes: until now, a
role's permissions were fixed at creation time (bootstrap or
company-create) with no API to change them afterwards. These tests prove
an already-existing role can have permissions added/removed live, and that
a user holding that role sees the change immediately (no re-login,
no new company needed).
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Settings Test Holding",
        "company_legal_name": "Settings Test Co.",
        "company_legal_name_ar": "شركة اختبار الإعدادات",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Settings Test Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    body = resp.json()
    company_id = body["company_id"]
    admin_role_id = body["admin_role_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return headers, company_id, admin_role_id


async def _create_user_with_role(client, headers, company_id, role_id):
    email = unique_email()
    password = "Str0ng!Passw0rd"
    create_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": email, "full_name": "Role Test User", "password": password, "company_id": company_id},
    )
    user_id = create_resp.json()["id"]
    assign_resp = await client.post(
        f"/api/v1/identity/users/{user_id}/roles", headers=headers, json={"role_id": role_id}
    )
    assert assign_resp.status_code == 204

    login_resp = await client.post("/api/v1/identity/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}


# --- Company Settings -------------------------------------------------


async def test_update_company_details(client):
    headers, company_id, _ = await _bootstrap_and_login(client)

    resp = await client.patch(
        f"/api/v1/identity/companies/{company_id}",
        headers=headers,
        json={
            "legal_name": "Updated Legal Name",
            "legal_name_ar": "الاسم القانوني المحدث",
            "vat_number": unique_vat(),
            "cr_number": "1010101010",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["legal_name"] == "Updated Legal Name"
    assert body["legal_name_ar"] == "الاسم القانوني المحدث"
    assert body["cr_number"] == "1010101010"

    get_resp = await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)
    assert get_resp.json()["legal_name"] == "Updated Legal Name"


async def test_update_company_rejects_duplicate_vat(client):
    headers_a, company_a, _ = await _bootstrap_and_login(client)
    headers_b, company_b, _ = await _bootstrap_and_login(client)

    company_a_data = await client.get(f"/api/v1/identity/companies/{company_a}", headers=headers_a)
    taken_vat = company_a_data.json()["vat_number"]

    resp = await client.patch(
        f"/api/v1/identity/companies/{company_b}",
        headers=headers_b,
        json={
            "legal_name": "Company B",
            "legal_name_ar": "شركة ب",
            "vat_number": taken_vat,
            "cr_number": None,
        },
    )
    assert resp.status_code == 422


async def test_update_company_requires_permission(client):
    headers, company_id, admin_role_id = await _bootstrap_and_login(client)
    no_perm_headers = await _create_user_with_role(client, headers, company_id, admin_role_id)

    # Strip the role down to nothing so this user has zero permissions.
    strip_resp = await client.put(
        f"/api/v1/identity/roles/{admin_role_id}/permissions",
        headers=headers,
        json={"permission_codes": [c for c, _ in _catalog_minus("company.manage")]},
    )
    assert strip_resp.status_code == 200

    resp = await client.patch(
        f"/api/v1/identity/companies/{company_id}",
        headers=no_perm_headers,
        json={"legal_name": "X", "legal_name_ar": "Y", "vat_number": unique_vat(), "cr_number": None},
    )
    assert resp.status_code == 403


def _catalog_minus(excluded_code: str):
    from src.shared.infrastructure.db.seed import PERMISSION_CATALOG

    return [(c, s) for c, s in PERMISSION_CATALOG if c != excluded_code]


# --- Security: Roles & Permissions -------------------------------------


async def test_list_permissions_returns_full_catalog(client):
    headers, _, _ = await _bootstrap_and_login(client)

    resp = await client.get("/api/v1/identity/permissions", headers=headers)
    assert resp.status_code == 200
    codes = {p["code"] for p in resp.json()}
    assert "role.manage" in codes
    assert "company.manage" in codes


async def test_list_roles_includes_admin(client):
    headers, _, admin_role_id = await _bootstrap_and_login(client)

    resp = await client.get("/api/v1/identity/roles", headers=headers)
    assert resp.status_code == 200
    role_ids = {r["id"] for r in resp.json()}
    assert admin_role_id in role_ids


async def test_create_role_starts_with_no_permissions(client):
    headers, _, _ = await _bootstrap_and_login(client)

    resp = await client.post("/api/v1/identity/roles", headers=headers, json={"name": "Sales Rep"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Sales Rep"
    assert body["is_system"] is False
    assert body["permission_codes"] == []


async def test_grant_and_revoke_permission_on_existing_role_takes_effect_live(client):
    """The core fix: a role created at bootstrap time (with the full
    catalog) can have a permission removed, and a *different* new
    permission granted, without recreating the company or the role."""
    headers, company_id, _ = await _bootstrap_and_login(client)

    create_resp = await client.post("/api/v1/identity/roles", headers=headers, json={"name": "Limited Role"})
    role_id = create_resp.json()["id"]

    limited_user_headers = await _create_user_with_role(client, headers, company_id, role_id)

    # Zero permissions initially — can't view partners.
    forbidden = await client.get("/api/v1/identity/partners", headers=limited_user_headers)
    assert forbidden.status_code == 403

    # Grant partner.view live.
    grant_resp = await client.put(
        f"/api/v1/identity/roles/{role_id}/permissions",
        headers=headers,
        json={"permission_codes": ["partner.view"]},
    )
    assert grant_resp.status_code == 200
    assert grant_resp.json()["permission_codes"] == ["partner.view"]

    allowed = await client.get("/api/v1/identity/partners", headers=limited_user_headers)
    assert allowed.status_code == 200

    # Revoke it again — access disappears immediately.
    revoke_resp = await client.put(
        f"/api/v1/identity/roles/{role_id}/permissions", headers=headers, json={"permission_codes": []}
    )
    assert revoke_resp.status_code == 200

    forbidden_again = await client.get("/api/v1/identity/partners", headers=limited_user_headers)
    assert forbidden_again.status_code == 403


async def test_update_role_permissions_rejects_unknown_code(client):
    headers, _, _ = await _bootstrap_and_login(client)
    create_resp = await client.post("/api/v1/identity/roles", headers=headers, json={"name": "Role X"})
    role_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/v1/identity/roles/{role_id}/permissions",
        headers=headers,
        json={"permission_codes": ["not.a.real.permission"]},
    )
    assert resp.status_code == 422


async def test_role_access_is_isolated_between_companies(client):
    headers_a, _, admin_role_a = await _bootstrap_and_login(client)
    headers_b, _, _ = await _bootstrap_and_login(client)

    resp = await client.get(f"/api/v1/identity/roles/{admin_role_a}", headers=headers_b)
    assert resp.status_code == 404


async def test_roles_endpoints_require_role_manage_permission(client):
    headers, company_id, admin_role_id = await _bootstrap_and_login(client)
    no_perm_headers = await _create_user_with_role(client, headers, company_id, admin_role_id)

    strip_resp = await client.put(
        f"/api/v1/identity/roles/{admin_role_id}/permissions",
        headers=headers,
        json={"permission_codes": [c for c, _ in _catalog_minus("role.manage")]},
    )
    assert strip_resp.status_code == 200

    resp = await client.get("/api/v1/identity/roles", headers=no_perm_headers)
    assert resp.status_code == 403
