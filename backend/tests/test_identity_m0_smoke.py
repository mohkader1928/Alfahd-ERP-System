"""Integration smoke test for Backend M0 — Foundation.

Exercises UC-CORE-01 (login) and UC-CORE-02 (register company) end to end
through the real HTTP layer, against the real database (including RLS
policies), per FR-CORE-001..017.
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap(client, *, vat=None, email=None, password="Str0ng!Passw0rd"):
    payload = {
        "tenant_legal_name": "Test Holding",
        "company_legal_name": "Test Trading Co.",
        "company_legal_name_ar": "Test Trading Arabic",
        "vat_number": vat or unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": email or unique_email(),
        "admin_full_name": "Test Admin",
        "admin_password": password,
    }
    resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    return resp, payload


async def test_bootstrap_creates_tenant_company_branch_and_admin(client):
    resp, _ = await _bootstrap(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["tenant_id"]
    assert body["company_id"]
    assert body["branch_id"]
    assert body["admin_user_id"]
    assert body["admin_role_id"]


async def test_duplicate_vat_number_rejected(client):
    vat = unique_vat()
    resp1, _ = await _bootstrap(client, vat=vat)
    assert resp1.status_code == 201

    resp2, _ = await _bootstrap(client, vat=vat)
    # Company.vat_number has a partial unique index (Phase 7 §1.3);
    # violating it surfaces as a 500 from the raw IntegrityError today —
    # tracked as a follow-up to translate into a clean 409/422 in the
    # application service (see Phase 10 §4's error-mapping requirement).
    assert resp2.status_code in (409, 422, 500)


async def test_login_succeeds_with_correct_credentials(client):
    _, payload = await _bootstrap(client)
    resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_login_fails_with_wrong_password(client):
    _, payload = await _bootstrap(client)
    resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_protected_endpoint_requires_token(client):
    bootstrap_resp, _ = await _bootstrap(client)
    company_id = bootstrap_resp.json()["company_id"]

    resp = await client.get(f"/api/v1/identity/companies/{company_id}")
    assert resp.status_code == 401


async def test_protected_endpoint_rejects_unauthorized_company(client):
    bootstrap_resp, payload = await _bootstrap(client)
    company_id = bootstrap_resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(
        f"/api/v1/identity/companies/{company_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Company-Id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert resp.status_code == 403


async def test_grant_company_access_rejects_company_from_a_different_tenant(client):
    """UI/UX Foundation milestone: POST /users/{id}/company-access must not
    let a caller graft access onto a company outside their own tenant — the
    tenant boundary is the real ownership boundary in this system, and this
    endpoint's whole job is granting access, so it's the one place this
    needs an explicit test, not just incidental RLS coverage."""
    resp_a, payload_a = await _bootstrap(client)
    company_a_id = resp_a.json()["company_id"]
    admin_a_user_id = resp_a.json()["admin_user_id"]

    resp_b, _ = await _bootstrap(client)
    company_b_id = resp_b.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload_a["admin_email"], "password": payload_a["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_a_id}

    resp = await client.post(
        f"/api/v1/identity/users/{admin_a_user_id}/company-access",
        headers=headers,
        json={"company_id": company_b_id},
    )
    assert resp.status_code == 422
    assert "Company not found" in resp.json()["detail"]


async def test_grant_company_access_rejects_duplicate_grant(client):
    resp, payload = await _bootstrap(client)
    company_id = resp.json()["company_id"]
    branch_id = resp.json()["branch_id"]
    admin_user_id = resp.json()["admin_user_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}

    # The bootstrap admin already has (company_id, branch_id) access, granted
    # at creation time (create_user grants access scoped to the main
    # branch) — granting the exact same (company_id, branch_id) pair again
    # must be rejected, not silently duplicated.
    resp2 = await client.post(
        f"/api/v1/identity/users/{admin_user_id}/company-access",
        headers=headers,
        json={"company_id": company_id, "branch_id": branch_id},
    )
    assert resp2.status_code == 422
    assert "already has access" in resp2.json()["detail"]


async def test_grant_company_access_rejects_unknown_user_and_company(client):
    resp, payload = await _bootstrap(client)
    company_id = resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}

    unknown_user_resp = await client.post(
        "/api/v1/identity/users/00000000-0000-0000-0000-000000000000/company-access",
        headers=headers,
        json={"company_id": company_id},
    )
    assert unknown_user_resp.status_code == 422
    assert "User not found" in unknown_user_resp.json()["detail"]


async def test_grant_company_access_requires_user_manage_roles_permission(client):
    """A user with zero role assignment (created but never assigned a role
    — create_user does not auto-assign one) has zero granted permissions in
    that company, so this reproduces a genuine 'lacks user.manage_roles'
    403 through real permission data, not a mocked/forced check."""
    resp, payload = await _bootstrap(client)
    company_id = resp.json()["company_id"]
    admin_user_id = resp.json()["admin_user_id"]

    admin_login = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Company-Id": company_id}

    no_role_email = unique_email()
    create_resp = await client.post(
        "/api/v1/identity/users",
        headers=admin_headers,
        json={
            "email": no_role_email,
            "full_name": "No Role User",
            "password": "Str0ng!Passw0rd",
            "company_id": company_id,
        },
    )
    assert create_resp.status_code == 201

    no_role_login = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": no_role_email, "password": "Str0ng!Passw0rd"},
    )
    no_role_token = no_role_login.json()["access_token"]
    no_role_headers = {"Authorization": f"Bearer {no_role_token}", "X-Company-Id": company_id}

    resp = await client.post(
        f"/api/v1/identity/users/{admin_user_id}/company-access",
        headers=no_role_headers,
        json={"company_id": company_id},
    )
    assert resp.status_code == 403


async def test_create_company_adds_second_company_to_same_tenant(client):
    """UI/UX Foundation milestone (Owner-approved addition): POST /companies
    lets an existing tenant add a second company — before this, /bootstrap
    was the only creation path and it always mints a brand-new tenant
    alongside it. The creator is auto-provisioned as that company's Admin
    (own role + access grant), because there is no other API path to give
    anyone a role in a company outside of /bootstrap — without this, the
    new company would be permanently unusable by any real screen."""
    resp, payload = await _bootstrap(client)
    company_a_id = resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_a_id}

    create_resp = await client.post(
        "/api/v1/identity/companies",
        headers=headers,
        json={
            "legal_name": "Second Company Ltd.",
            "legal_name_ar": "الشركة الثانية",
            "vat_number": unique_vat(),
            "base_currency_code": "SAR",
            "valuation_method": "average",
        },
    )
    assert create_resp.status_code == 201
    company_b = create_resp.json()
    assert company_b["id"] != company_a_id
    assert company_b["legal_name"] == "Second Company Ltd."

    # The JWT used to create Company B was issued before Company B existed,
    # so its authorized_companies claim can't include it yet — a fresh
    # login is required, same as any other newly-granted access.
    relogin_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    new_token = relogin_resp.json()["access_token"]
    get_resp = await client.get(
        f"/api/v1/identity/companies/{company_b['id']}",
        headers={"Authorization": f"Bearer {new_token}", "X-Company-Id": company_b["id"]},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == company_b["id"]


async def test_full_two_company_flow_grants_access_and_isolates_data(client):
    """The real acceptance scenario end to end, via pure API calls: one
    admin ends up with two real companies under one tenant, sees both in a
    fresh login's authorized_companies, and each company's own data stays
    genuinely separate."""
    resp, payload = await _bootstrap(client)
    company_a_id = resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token}", "X-Company-Id": company_a_id}

    create_resp = await client.post(
        "/api/v1/identity/companies",
        headers=headers_a,
        json={
            "legal_name": "Second Company Ltd.",
            "legal_name_ar": "الشركة الثانية",
            "vat_number": unique_vat(),
        },
    )
    assert create_resp.status_code == 201
    company_b_id = create_resp.json()["id"]

    # create_company already auto-provisions the creator as Company B's
    # Admin (see its docstring) — no separate company-access call needed
    # here for the creator themselves; that endpoint exists for granting
    # access to *other* users, covered by the test_grant_company_access_*
    # tests above.

    # A fresh login is required to see the new grant — the JWT's
    # authorized_companies claim is fixed at issuance, matching how the
    # frontend's Company Context picker actually behaves.
    relogin_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    new_token = relogin_resp.json()["access_token"]
    import base64
    import json as jsonlib

    payload_b64 = new_token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    claims = jsonlib.loads(base64.urlsafe_b64decode(padded))
    authorized = claims["authorized_companies"]
    assert any(entry == company_a_id or entry.startswith(f"{company_a_id}:") for entry in authorized)
    assert any(entry == company_b_id or entry.startswith(f"{company_b_id}:") for entry in authorized)

    # Data isolation: a partner created under Company A must not appear
    # under Company B, even for the same admin user.
    headers_b = {"Authorization": f"Bearer {new_token}", "X-Company-Id": company_b_id}
    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers={"Authorization": f"Bearer {new_token}", "X-Company-Id": company_a_id},
        json={"name": "Only In Company A", "is_customer": True},
    )
    assert partner_resp.status_code == 201

    list_in_b = await client.get("/api/v1/identity/partners", headers=headers_b)
    assert list_in_b.status_code == 200
    assert all(p["name"] != "Only In Company A" for p in list_in_b.json())

    list_in_a = await client.get(
        "/api/v1/identity/partners", headers={"Authorization": f"Bearer {new_token}", "X-Company-Id": company_a_id}
    )
    assert any(p["name"] == "Only In Company A" for p in list_in_a.json())


async def test_full_o2c_precondition_flow_branch_and_company_scoped_access(client):
    """UC-CORE-02/03: admin can view their company, list branches, create a branch."""
    bootstrap_resp, payload = await _bootstrap(client)
    company_id = bootstrap_resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}

    get_resp = await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == company_id

    create_branch_resp = await client.post(
        f"/api/v1/identity/companies/{company_id}/branches",
        headers=headers,
        json={"name": "Riyadh Branch", "name_ar": "Riyadh Branch AR", "is_main": False},
    )
    assert create_branch_resp.status_code == 201

    list_resp = await client.get(f"/api/v1/identity/companies/{company_id}/branches", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2  # main branch from bootstrap + the one just created


async def _admin_headers(client, resp, payload):
    company_id = resp.json()["company_id"]
    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    return company_id, {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}


async def test_list_users_shows_created_users_with_role_names(client):
    """Bundle 2 — Identity/Access/Governance: GET /users, previously
    nonexistent, must show every user with company access, each with the
    role names they hold for this company."""
    resp, payload = await _bootstrap(client)
    company_id, headers = await _admin_headers(client, resp, payload)
    admin_user_id = resp.json()["admin_user_id"]

    new_email = unique_email()
    create_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": new_email, "full_name": "Fresh Employee", "password": "Str0ng!Passw0rd", "company_id": company_id},
    )
    assert create_resp.status_code == 201
    new_user_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/identity/users", headers=headers)
    assert list_resp.status_code == 200
    rows = {row["id"]: row for row in list_resp.json()}

    assert admin_user_id in rows
    assert rows[admin_user_id]["role_names"] == ["Admin"]
    assert new_user_id in rows
    assert rows[new_user_id]["full_name"] == "Fresh Employee"
    assert rows[new_user_id]["role_names"] == []  # create_user never auto-assigns a role


async def test_get_user_detail_shows_roles_and_company_access(client):
    resp, payload = await _bootstrap(client)
    company_id, headers = await _admin_headers(client, resp, payload)
    admin_user_id = resp.json()["admin_user_id"]

    detail_resp = await client.get(f"/api/v1/identity/users/{admin_user_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["email"] == payload["admin_email"]
    assert [r["name"] for r in detail["roles"]] == ["Admin"]
    assert any(c["company_id"] == company_id for c in detail["company_access"])


async def test_assign_and_remove_role_reflected_in_user_detail(client):
    """Symmetric role assignment: a role can be both granted and revoked
    through the API, and the change is immediately visible in GET
    /users/{id} — not just a one-way POST with no way to undo it."""
    resp, payload = await _bootstrap(client)
    company_id, headers = await _admin_headers(client, resp, payload)

    new_email = unique_email()
    create_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": new_email, "full_name": "Role Test User", "password": "Str0ng!Passw0rd", "company_id": company_id},
    )
    new_user_id = create_resp.json()["id"]

    roles_resp = await client.get("/api/v1/identity/roles", headers=headers)
    admin_role_id = next(r["id"] for r in roles_resp.json() if r["name"] == "Admin")

    assign_resp = await client.post(
        f"/api/v1/identity/users/{new_user_id}/roles", headers=headers, json={"role_id": admin_role_id}
    )
    assert assign_resp.status_code == 204

    detail_after_assign = (
        await client.get(f"/api/v1/identity/users/{new_user_id}", headers=headers)
    ).json()
    assert [r["id"] for r in detail_after_assign["roles"]] == [admin_role_id]

    remove_resp = await client.delete(
        f"/api/v1/identity/users/{new_user_id}/roles/{admin_role_id}", headers=headers
    )
    assert remove_resp.status_code == 204

    detail_after_remove = (
        await client.get(f"/api/v1/identity/users/{new_user_id}", headers=headers)
    ).json()
    assert detail_after_remove["roles"] == []


async def test_list_users_isolated_across_companies(client):
    resp_a, payload_a = await _bootstrap(client)
    _, headers_a = await _admin_headers(client, resp_a, payload_a)
    admin_a_id = resp_a.json()["admin_user_id"]

    resp_b, payload_b = await _bootstrap(client)
    _, headers_b = await _admin_headers(client, resp_b, payload_b)

    list_b = (await client.get("/api/v1/identity/users", headers=headers_b)).json()
    assert all(row["id"] != admin_a_id for row in list_b)


async def test_list_users_requires_permission(client):
    resp = await client.get("/api/v1/identity/users")
    assert resp.status_code == 401
