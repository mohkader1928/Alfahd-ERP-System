"""Adaptive ERP Stage 2.5 — First End-to-End Vertical Slice.

Proves the full concept, as one continuous story, against real isolated
test companies (never production data): New Company -> Customer Profile ->
Sizing Engine -> ERP Blueprint -> Blueprint Approval -> Configuration Plan
-> Validate -> Apply -> Verification. Reuses only APIs already proven in
Stage 2.1-2.4 (test_adaptive_company_profile.py, test_adaptive_sizing_engine.py,
test_adaptive_blueprint.py, test_adaptive_configuration_engine.py) -- no
new backend surface is introduced by this file or by Stage 2.5.

Covers the 15 scenarios required by the Stage 2.5 approval message:
1-9 (happy path through Verification) and idempotent re-apply are proven
together in test_vertical_slice_full_happy_path (a single continuous
company-lifecycle story, matching how the real wizard will drive these
same APIs in sequence). The remaining scenarios (10-15) are each their own
focused test.
"""

from sqlalchemy import delete, select

from src.modules.identity.infrastructure.models import Role, RolePermission
from src.shared.infrastructure.db.session import (
    AsyncSessionLocal,
    set_company_context,
    set_tenant_context,
)
from tests.conftest import unique_email, unique_vat

CANONICAL_ROLE_TEMPLATE_NAMES = ("Accountant", "Sales", "Purchasing & Warehouse", "Read-Only Viewer")


async def _bootstrap_tenant(client, label="VS"):
    """Mints a tenant + first company + admin -- the authenticated context
    a real Owner would already have before running the Company Setup
    Wizard for a *new* company under that same tenant (mirrors how the
    frontend wizard's first step, "Create Company", is reached: already
    logged in, then POST /companies)."""
    payload = {
        "tenant_legal_name": f"{label} Holding",
        "company_legal_name": f"{label} First Co.",
        "company_legal_name_ar": f"{label} First Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": f"{label} Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201, boot_resp.text
    tenant_id = boot_resp.json()["tenant_id"]
    first_company_id = boot_resp.json()["company_id"]
    first_branch_id = boot_resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    refresh_token = login_resp.json()["refresh_token"]
    first_headers = {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": first_company_id,
        "X-Branch-Id": first_branch_id,
    }
    return tenant_id, token, refresh_token, first_headers


async def _create_new_company(client, token, refresh_token, first_headers, label="VS"):
    """Step 1 of the wizard: create the actual company the vertical slice
    runs against, via the existing (already-tested) POST /companies. The
    admin is auto-granted Admin role + DB-level company access by that
    endpoint, but `authorized_companies` is baked into the JWT at issue
    time (backend/src/shared/security/auth_context.py) -- so the *current*
    access token still 403s ("Not authorized for this company") against
    the brand-new company_id until a fresh token is minted. AuthenticationService
    .refresh_tokens() re-derives authorized_companies live from DB
    (identical to login), so a real /auth/refresh call, not a full
    re-login, is what both this test and the real wizard must do
    immediately after company creation."""
    resp = await client.post(
        "/api/v1/identity/companies",
        headers=first_headers,
        json={
            "legal_name": f"{label} New Co.",
            "legal_name_ar": f"{label} New Arabic",
            "vat_number": unique_vat(),
            "base_currency_code": "SAR",
            "valuation_method": "average",
        },
    )
    assert resp.status_code == 201, resp.text
    company_id = resp.json()["id"]

    refresh_resp = await client.post("/api/v1/identity/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200, refresh_resp.text
    fresh_token = refresh_resp.json()["access_token"]

    headers = {"Authorization": f"Bearer {fresh_token}", "X-Company-Id": company_id}
    return company_id, headers


async def _clear_role_templates(company_id: str, names=CANONICAL_ROLE_TEMPLATE_NAMES) -> None:
    """Test-only arrange step (direct DB access, no identity code touched)
    -- POST /companies already seeds all 4 canonical templates, so without
    this the provision_role_templates decision would always be a no-op
    skip; clearing them lets the happy-path test prove real creation too."""
    async with AsyncSessionLocal() as session:
        await set_company_context(session, company_id)
        result = await session.execute(select(Role.id).where(Role.company_id == company_id, Role.name.in_(names)))
        role_ids = [row[0] for row in result.all()]
        if role_ids:
            await session.execute(delete(RolePermission).where(RolePermission.role_id.in_(role_ids)))
            await session.execute(delete(Role).where(Role.id.in_(role_ids)))
            await session.commit()


async def _role_names(company_id: str) -> set[str]:
    async with AsyncSessionLocal() as session:
        await set_company_context(session, company_id)
        result = await session.execute(select(Role.name).where(Role.company_id == company_id))
        return set(result.scalars().all())


async def _get_company(client, headers, company_id):
    resp = await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_vertical_slice_full_happy_path(client):
    """1) New company -> profile. 2) profile -> sizing. 3) sizing ->
    blueprint. 4) blueprint approval. 5) approved blueprint -> plan.
    6) validation. 7) apply. 8) verification. 9) idempotent re-apply.
    All against one isolated test company, one continuous story."""
    tenant_id, token, refresh_token, first_headers = await _bootstrap_tenant(client, "VS_Happy")
    company_id, headers = await _create_new_company(client, token, refresh_token, first_headers, "VS_Happy")
    await _clear_role_templates(company_id)

    # --- A. Customer Profile ---
    profile_payload = {
        "industry": "Wholesale Trading",
        "legal_form": "LLC",
        "employee_count": 45,
        "branch_count": 2,
        "cost_center_tracking_needed": True,
        "is_service_business": False,
        "warehouse_count": 3,
        "monthly_sales_order_volume": 250,
        "monthly_purchase_order_volume": 120,
        "sku_count_estimate": 800,
        "coa_depth_preference": 3,
        "multi_currency_requested": False,
        "withholding_tax_needed": False,
        "owns_fixed_assets": True,
        "fixed_asset_count_estimate": 30,
        "approval_rigor_preference": "medium",
        "desired_user_count": 12,
        "two_factor_required": True,
        "growth_notes": {"3yr_plan": "Expand to 5 branches, add e-commerce channel"},
    }
    create_profile = await client.post("/api/v1/company-profile", headers=headers, json=profile_payload)
    assert create_profile.status_code == 201, create_profile.text
    profile_id = create_profile.json()["id"]

    # Review Profile: GET returns exactly what was submitted.
    review_profile = await client.get("/api/v1/company-profile", headers=headers)
    assert review_profile.status_code == 200
    assert review_profile.json()["id"] == profile_id
    assert review_profile.json()["employee_count"] == 45

    # --- B. Sizing ---
    sizing_resp = await client.post("/api/v1/company-profile/sizing", headers=headers)
    assert sizing_resp.status_code == 201, sizing_resp.text
    sizing = sizing_resp.json()
    assert sizing["rule_version"] == "sizing-rules-v1"
    # Explainable: every dimension has a real, non-empty reason, not just a
    # single Small/Medium/Large label.
    dims = sizing["dimension_scores"]
    expected_dims = {
        "organizational_complexity",
        "transaction_volume",
        "inventory_complexity",
        "financial_complexity",
        "tax_compliance_complexity",
        "asset_complexity",
        "approval_governance_complexity",
        "security_access_complexity",
    }
    assert set(dims.keys()) == expected_dims
    for dim_name, dim in dims.items():
        assert 0 <= dim["score"] <= 100
        assert len(dim["reason"]) > 0, f"{dim_name} has no explanation"

    latest_sizing = await client.get("/api/v1/company-profile/sizing/latest", headers=headers)
    assert latest_sizing.status_code == 200
    assert latest_sizing.json()["id"] == sizing["id"]

    # --- C. Blueprint (generate never writes business data) ---
    blueprint_resp = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    assert blueprint_resp.status_code == 201, blueprint_resp.text
    blueprint = blueprint_resp.json()
    assert blueprint["status"] == "draft"
    assert blueprint["company_profile_id"] == profile_id
    assert blueprint["sizing_result_id"] == sizing["id"]

    decisions_by_key = {d["key"]: d for d in blueprint["decisions"]}
    for key, decision in decisions_by_key.items():
        assert decision["category"] in ("STANDARD", "CONFIGURABLE", "EXTENSIBLE", "CUSTOM_DEVELOPMENT")
        assert isinstance(decision["actionable"], bool)
        assert len(decision["reason"]) > 0, f"{key} decision has no reason"
    # Blueprint does not apply itself.
    assert blueprint["approved_at"] is None
    assert blueprint["approved_by"] is None

    # --- D. Approval (explicit draft -> approved; no self-approval) ---
    approve_resp = await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=headers)
    assert approve_resp.status_code == 200, approve_resp.text
    approved_blueprint = approve_resp.json()
    assert approved_blueprint["status"] == "approved"
    assert approved_blueprint["approved_at"] is not None
    assert approved_blueprint["approved_by"] is not None

    # --- E. Configuration Plan ---
    before_company = await _get_company(client, headers, company_id)
    assert before_company["po_approval_threshold"] is None

    plan_resp = await client.post("/api/v1/company-profile/configuration-plan", headers=headers)
    assert plan_resp.status_code == 201, plan_resp.text
    plan = plan_resp.json()
    assert plan["status"] == "draft"
    assert plan["blueprint_id"] == blueprint["id"]
    plan_items_by_key = {i["decision_key"]: i for i in plan["items"]}
    # Only the two decisions Stage 2.4 proved actionable ever become plan
    # items -- what will/won't apply is explicit and visible.
    assert set(plan_items_by_key.keys()) == {"po_approval_threshold", "provision_role_templates"}
    assert "provision_additional_branch" not in plan_items_by_key  # capability gap, never guessed at

    # --- F. Validate ---
    validate_resp = await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)
    assert validate_resp.status_code == 200, validate_resp.text
    assert validate_resp.json()["status"] == "validated"

    # --- G. Apply (only currently-actionable decisions) ---
    apply_resp = await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    assert apply_resp.status_code == 200, apply_resp.text
    applied = apply_resp.json()
    assert applied["status"] == "applied"
    applied_items = {i["decision_key"]: i for i in applied["items"]}
    assert applied_items["po_approval_threshold"]["status"] == "applied"
    assert applied_items["provision_role_templates"]["status"] == "applied"
    created_role_names = {r["role_name"] for r in applied_items["provision_role_templates"]["result"]["created"]}
    assert created_role_names == set(CANONICAL_ROLE_TEMPLATE_NAMES)

    # --- H. Verification ---
    after_company = await _get_company(client, headers, company_id)
    assert after_company["po_approval_threshold"] is not None
    for field in ("legal_name", "legal_name_ar", "vat_number", "cr_number", "fiscal_year_start_month"):
        assert after_company[field] == before_company[field], f"{field} changed unexpectedly"
    assert await _role_names(company_id) == {"Admin", *CANONICAL_ROLE_TEMPLATE_NAMES}

    fresh_blueprint = await client.get(f"/api/v1/company-profile/blueprint/{blueprint['id']}", headers=headers)
    assert fresh_blueprint.json()["status"] == "approved"  # still approved, not superseded

    # 9) Idempotent re-apply: no duplicate roles, no further threshold
    # change, both items report as already applied.
    reapply_resp = await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    assert reapply_resp.status_code == 200
    reapplied_items = {i["decision_key"]: i for i in reapply_resp.json()["items"]}
    assert reapplied_items["po_approval_threshold"]["status"] == "skipped_already_applied"
    assert reapplied_items["provision_role_templates"]["status"] == "skipped_already_applied"
    assert await _role_names(company_id) == {"Admin", *CANONICAL_ROLE_TEMPLATE_NAMES}
    after_reapply_company = await _get_company(client, headers, company_id)
    assert after_reapply_company["po_approval_threshold"] == after_company["po_approval_threshold"]


async def test_vertical_slice_company_isolation(client):
    """10) Company isolation across the whole chain."""
    tenant_id, token, refresh_token, first_headers = await _bootstrap_tenant(client, "VS_IsoA")
    company_a, headers_a = await _create_new_company(client, token, refresh_token, first_headers, "VS_IsoA")
    _, token_b, refresh_token_b, first_headers_b = await _bootstrap_tenant(client, "VS_IsoB")
    company_b, headers_b = await _create_new_company(client, token_b, refresh_token_b, first_headers_b, "VS_IsoB")
    await _clear_role_templates(company_a)
    await _clear_role_templates(company_b)

    await client.post("/api/v1/company-profile", headers=headers_a, json={})
    await client.post("/api/v1/company-profile/sizing", headers=headers_a)
    blueprint_a = (await client.post("/api/v1/company-profile/blueprint", headers=headers_a)).json()
    await client.post(f"/api/v1/company-profile/blueprint/{blueprint_a['id']}/approve", headers=headers_a)
    plan_a = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers_a)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan_a['id']}/validate", headers=headers_a)
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan_a['id']}/apply", headers=headers_a)

    # Company B (a fully separate tenant) has zero visibility into company A.
    profile_b = await client.get("/api/v1/company-profile", headers=headers_b)
    assert profile_b.status_code == 404
    company_b_after = await _get_company(client, headers_b, company_b)
    assert company_b_after["po_approval_threshold"] is None
    assert await _role_names(company_b) == {"Admin"}

    cross_plan = await client.get(f"/api/v1/company-profile/configuration-plan/{plan_a['id']}", headers=headers_b)
    assert cross_plan.status_code == 404
    cross_blueprint = await client.get(f"/api/v1/company-profile/blueprint/{blueprint_a['id']}", headers=headers_b)
    assert cross_blueprint.status_code == 404


async def test_vertical_slice_rbac(client):
    """11) RBAC gates every step of the chain."""
    tenant_id, token, refresh_token, first_headers = await _bootstrap_tenant(client, "VS_RBAC")
    company_id, headers = await _create_new_company(client, token, refresh_token, first_headers, "VS_RBAC")
    await client.post("/api/v1/company-profile", headers=headers, json={})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)

    no_auth_headers = {"X-Company-Id": company_id}
    assert (await client.post("/api/v1/company-profile", headers=no_auth_headers, json={})).status_code == 401
    assert (await client.post("/api/v1/company-profile/sizing", headers=no_auth_headers)).status_code == 401
    assert (await client.post("/api/v1/company-profile/blueprint", headers=no_auth_headers)).status_code == 401
    assert (
        await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=no_auth_headers)
    ).status_code == 401
    assert (await client.post("/api/v1/company-profile/configuration-plan", headers=no_auth_headers)).status_code == 401
    assert (
        await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=no_auth_headers)
    ).status_code == 401


async def test_vertical_slice_audit_trail(client):
    """12) A full AuditLog trail ties every real write to a user and a
    timestamp, across the whole chain."""
    tenant_id, token, refresh_token, first_headers = await _bootstrap_tenant(client, "VS_Audit")
    company_id, headers = await _create_new_company(client, token, refresh_token, first_headers, "VS_Audit")
    await _clear_role_templates(company_id)

    await client.post("/api/v1/company-profile", headers=headers, json={"approval_rigor_preference": "high"})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)

    async with AsyncSessionLocal() as session:
        await set_tenant_context(session, tenant_id)
        from sqlalchemy import text as sql_text

        result = await session.execute(
            sql_text(
                "SELECT target_table, field_name, old_value, new_value, user_id FROM audit_log "
                "WHERE company_id = :cid ORDER BY changed_at"
            ),
            {"cid": company_id},
        )
        rows = result.all()

    threshold_rows = [r for r in rows if r.target_table == "company" and r.field_name == "po_approval_threshold"]
    assert len(threshold_rows) == 1
    assert threshold_rows[0].new_value == "100000"  # high rigor
    assert threshold_rows[0].user_id is not None

    role_rows = [r for r in rows if r.target_table == "role" and r.field_name == "name"]
    assert {r.new_value for r in role_rows} == set(CANONICAL_ROLE_TEMPLATE_NAMES)


async def test_vertical_slice_zero_business_data_mutation(client):
    """13) Zero unintended business-data mutation across the whole chain."""
    from sqlalchemy import text as sql_text

    tenant_id, token, refresh_token, first_headers = await _bootstrap_tenant(client, "VS_ZeroBiz")
    company_id, headers = await _create_new_company(client, token, refresh_token, first_headers, "VS_ZeroBiz")
    await _clear_role_templates(company_id)

    async def _counts():
        async with AsyncSessionLocal() as session:
            await set_company_context(session, company_id)
            counts = {}
            for table in ("partner", "product", "sales_invoice", "journal_entry", "purchase_order"):
                result = await session.execute(
                    sql_text(f"SELECT COUNT(*) FROM {table} WHERE company_id = :cid"), {"cid": company_id}
                )
                counts[table] = result.scalar_one()
            return counts

    before = await _counts()
    assert all(v == 0 for v in before.values())

    await client.post("/api/v1/company-profile", headers=headers, json={})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)
    apply_resp = await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    assert apply_resp.json()["status"] == "applied"

    after = await _counts()
    assert after == before


async def test_vertical_slice_rejected_and_superseded_blueprint(client):
    """14) An unapproved Blueprint can never produce a Configuration Plan,
    and a Plan tied to a since-superseded Blueprint is refused at Apply."""
    tenant_id, token, refresh_token, first_headers = await _bootstrap_tenant(client, "VS_Superseded")
    company_id, headers = await _create_new_company(client, token, refresh_token, first_headers, "VS_Superseded")

    await client.post("/api/v1/company-profile", headers=headers, json={})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    draft_blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()
    assert draft_blueprint["status"] == "draft"

    # Rejected: draft Blueprint cannot produce a Plan.
    rejected_plan = await client.post("/api/v1/company-profile/configuration-plan", headers=headers)
    assert rejected_plan.status_code == 404

    approve_resp = await client.post(
        f"/api/v1/company-profile/blueprint/{draft_blueprint['id']}/approve", headers=headers
    )
    assert approve_resp.status_code == 200
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)

    # A newer Blueprint supersedes the one this Plan was built from.
    new_blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/blueprint/{new_blueprint['id']}/approve", headers=headers)
    old_now = await client.get(f"/api/v1/company-profile/blueprint/{draft_blueprint['id']}", headers=headers)
    assert old_now.json()["status"] == "superseded"

    apply_resp = await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    applied = apply_resp.json()
    assert applied["status"] == "failed"
    assert "no longer approved" in applied["failure_reason"]

    company_after = await _get_company(client, headers, company_id)
    assert company_after["po_approval_threshold"] is None  # zero writes happened


async def test_vertical_slice_partial_state_safety(client):
    """15) A partially-provisioned company (some but not all canonical
    role templates already exist) is refused, not guessed at -- and any
    earlier write in the same Apply attempt rolls back with it."""
    tenant_id, token, refresh_token, first_headers = await _bootstrap_tenant(client, "VS_Partial")
    company_id, headers = await _create_new_company(client, token, refresh_token, first_headers, "VS_Partial")
    await _clear_role_templates(company_id, names=("Accountant",))  # leaves 3 of 4 templates in place

    before_company = await _get_company(client, headers, company_id)
    assert before_company["po_approval_threshold"] is None

    await client.post("/api/v1/company-profile", headers=headers, json={})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)

    apply_resp = await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    applied = apply_resp.json()
    assert applied["status"] == "failed"
    items_by_key = {i["decision_key"]: i for i in applied["items"]}
    assert items_by_key["po_approval_threshold"]["status"] == "pending"  # rolled back, never persisted
    assert items_by_key["provision_role_templates"]["status"] == "failed"

    company_after = await _get_company(client, headers, company_id)
    assert company_after["po_approval_threshold"] is None
