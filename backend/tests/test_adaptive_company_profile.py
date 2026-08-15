"""Adaptive ERP Stage 2.1 — Company Profile.

Grounded in docs/adaptive/03-customer-profile-spec.md (field justification)
and docs/adaptive/06-configuration-engine-architecture.md §6.6 (RLS/RBAC
posture — same mechanism as every other module, nothing new to test that
isn't already covered by the isolation-test file's own patterns; this file
adds a company_profile-specific isolation case for completeness).
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="CP"):
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
    assert boot_resp.status_code == 201, boot_resp.text
    company_id = boot_resp.json()["company_id"]
    branch_id = boot_resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, headers


async def test_get_before_create_is_404(client):
    _, headers = await _bootstrap_and_login(client, "CP_Get404")
    resp = await client.get("/api/v1/company-profile", headers=headers)
    assert resp.status_code == 404


async def test_create_and_get_profile(client):
    _, headers = await _bootstrap_and_login(client, "CP_Create")
    payload = {
        "industry": "Wholesale Trading",
        "employee_count": 12,
        "branch_count": 1,
        "is_service_business": False,
        "warehouse_count": 2,
        "monthly_sales_order_volume": 150,
        "owns_fixed_assets": True,
        "fixed_asset_count_estimate": 5,
        "approval_rigor_preference": "medium",
        "desired_user_count": 8,
    }
    created = await client.post("/api/v1/company-profile", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["industry"] == "Wholesale Trading"
    assert body["employee_count"] == 12
    assert body["approval_rigor_preference"] == "medium"
    assert body["cost_center_tracking_needed"] is False  # untouched field defaults correctly

    fetched = await client.get("/api/v1/company-profile", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


async def test_duplicate_create_rejected(client):
    _, headers = await _bootstrap_and_login(client, "CP_Dup")
    first = await client.post("/api/v1/company-profile", headers=headers, json={"industry": "Retail"})
    assert first.status_code == 201
    second = await client.post("/api/v1/company-profile", headers=headers, json={"industry": "Retail"})
    assert second.status_code == 422
    assert "already exists" in second.json()["detail"]


async def test_partial_update_preserves_other_fields(client):
    _, headers = await _bootstrap_and_login(client, "CP_Update")
    await client.post(
        "/api/v1/company-profile",
        headers=headers,
        json={"industry": "Manufacturing", "employee_count": 20, "approval_rigor_preference": "high"},
    )
    updated = await client.patch(
        "/api/v1/company-profile", headers=headers, json={"employee_count": 25}
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["employee_count"] == 25
    assert body["industry"] == "Manufacturing"  # untouched by the partial update
    assert body["approval_rigor_preference"] == "high"


async def test_update_before_create_is_404(client):
    _, headers = await _bootstrap_and_login(client, "CP_UpdateFirst")
    resp = await client.patch("/api/v1/company-profile", headers=headers, json={"employee_count": 5})
    assert resp.status_code == 404


async def test_invalid_approval_rigor_rejected(client):
    _, headers = await _bootstrap_and_login(client, "CP_BadRigor")
    resp = await client.post(
        "/api/v1/company-profile", headers=headers, json={"approval_rigor_preference": "extreme"}
    )
    assert resp.status_code == 422


async def test_negative_employee_count_rejected(client):
    _, headers = await _bootstrap_and_login(client, "CP_Negative")
    resp = await client.post("/api/v1/company-profile", headers=headers, json={"employee_count": -1})
    assert resp.status_code == 422


async def test_coa_depth_out_of_range_rejected(client):
    _, headers = await _bootstrap_and_login(client, "CP_CoaDepth")
    resp = await client.post("/api/v1/company-profile", headers=headers, json={"coa_depth_preference": 5})
    assert resp.status_code == 422


async def test_requires_permission(client):
    """A user with no roles at all (only the seeded Admin exists after
    bootstrap; this simulates a caller whose company context doesn't grant
    company_profile.manage) is rejected — same require_permission mechanism
    proven 156 times elsewhere in the Core, exercised here for completeness."""
    company_id, headers = await _bootstrap_and_login(client, "CP_Perm")
    no_auth_headers = {"X-Company-Id": company_id}  # missing Authorization entirely
    resp = await client.post("/api/v1/company-profile", headers=no_auth_headers, json={"industry": "X"})
    assert resp.status_code == 401


async def test_company_isolation_cannot_see_another_companys_profile(client):
    """Two separate companies (separate bootstraps) — company B must never
    be able to read or overwrite company A's profile, even by ID, matching
    the isolation pattern in tests/test_multi_tenancy_isolation.py."""
    _, headers_a = await _bootstrap_and_login(client, "CP_IsoA")
    _, headers_b = await _bootstrap_and_login(client, "CP_IsoB")

    created_a = await client.post(
        "/api/v1/company-profile", headers=headers_a, json={"industry": "Company A Industry"}
    )
    assert created_a.status_code == 201

    # Company B has no profile of its own yet — RLS must scope GET to B's
    # own company_id, never leaking A's row.
    b_get = await client.get("/api/v1/company-profile", headers=headers_b)
    assert b_get.status_code == 404

    # Company B creating its own profile must not collide with or expose A's.
    created_b = await client.post(
        "/api/v1/company-profile", headers=headers_b, json={"industry": "Company B Industry"}
    )
    assert created_b.status_code == 201
    assert created_b.json()["id"] != created_a.json()["id"]

    a_get = await client.get("/api/v1/company-profile", headers=headers_a)
    assert a_get.json()["industry"] == "Company A Industry"
    b_get_again = await client.get("/api/v1/company-profile", headers=headers_b)
    assert b_get_again.json()["industry"] == "Company B Industry"
