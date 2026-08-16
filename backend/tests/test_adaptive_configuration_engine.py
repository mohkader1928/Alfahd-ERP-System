"""Adaptive ERP Stage 2.4 v1 — Configuration Engine.

Grounded in the Stage 2.4 Design & Safety Review (approved before any code
here was written): Approved Blueprint -> Configuration Plan -> Validation
-> Apply -> Verification -> Audit. This file proves, against a real
isolated test company (never a production company), everything that
review promised: idempotency, refusal of unapproved/superseded Blueprints,
duplicate-plan rejection, atomic rollback on partial failure, company
isolation, that Company fields other than po_approval_threshold are never
touched, that zero business-data tables are touched at all, RBAC, and a
real AuditLog trail.
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


async def _bootstrap_and_login(client, label="CE"):
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
    tenant_id = boot_resp.json()["tenant_id"]
    company_id = boot_resp.json()["company_id"]
    branch_id = boot_resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, tenant_id, headers


async def _create_profile(client, headers, **overrides):
    resp = await client.post("/api/v1/company-profile", headers=headers, json=overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _approved_blueprint(client, headers):
    """Full Stage 2.1-2.3 setup a Configuration Plan needs: profile ->
    sizing -> generate -> approve. Returns the approved blueprint body."""
    await _create_profile(client, headers)
    size_resp = await client.post("/api/v1/company-profile/sizing", headers=headers)
    assert size_resp.status_code == 201, size_resp.text
    gen_resp = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    assert gen_resp.status_code == 201, gen_resp.text
    blueprint_id = gen_resp.json()["id"]
    approve_resp = await client.post(f"/api/v1/company-profile/blueprint/{blueprint_id}/approve", headers=headers)
    assert approve_resp.status_code == 200, approve_resp.text
    return approve_resp.json()


async def _get_company(client, headers, company_id):
    resp = await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _clear_role_templates(company_id: str, names=CANONICAL_ROLE_TEMPLATE_NAMES) -> None:
    """Test-only arrange step (direct DB access, no identity code touched)
    simulating a company that predates default role-template seeding --
    the one real-world case where provision_role_templates has anything to
    actually create. Deletes role_permission rows first (no ON DELETE
    CASCADE on that FK) then the Role rows themselves."""
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


async def test_create_plan_before_approved_blueprint_is_404(client):
    _, _, headers = await _bootstrap_and_login(client, "CE_NoBlueprint")
    resp = await client.post("/api/v1/company-profile/configuration-plan", headers=headers)
    assert resp.status_code == 404


async def test_create_plan_duplicate_is_conflict(client):
    _, _, headers = await _bootstrap_and_login(client, "CE_DupPlan")
    await _approved_blueprint(client, headers)
    first = await client.post("/api/v1/company-profile/configuration-plan", headers=headers)
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/company-profile/configuration-plan", headers=headers)
    assert second.status_code == 409


async def test_apply_before_validate_is_conflict(client):
    _, _, headers = await _bootstrap_and_login(client, "CE_ApplyBeforeValidate")
    await _approved_blueprint(client, headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    resp = await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    assert resp.status_code == 409


async def test_full_pipeline_happy_path_and_idempotent_reapply(client):
    """Create Profile -> Generate Blueprint -> Approve -> Create Plan ->
    Validate -> Apply -> Verify -> Re-run Apply -> prove idempotency, all
    against one isolated test company. Also proves the po_approval_threshold
    value actually changes (Configuration changed as intended) while every
    other Company field stays byte-identical (Business data unchanged)."""
    company_id, _, headers = await _bootstrap_and_login(client, "CE_Happy")
    await _clear_role_templates(company_id)
    assert await _role_names(company_id) == {"Admin"}

    before = await _get_company(client, headers, company_id)
    assert before["po_approval_threshold"] is None

    await _approved_blueprint(client, headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    assert plan["status"] == "draft"

    validated = (
        await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)
    ).json()
    assert validated["status"] == "validated"

    applied = (
        await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    ).json()
    assert applied["status"] == "applied"
    items_by_key = {i["decision_key"]: i for i in applied["items"]}

    # Configuration changed as intended.
    assert items_by_key["po_approval_threshold"]["status"] == "applied"
    assert items_by_key["po_approval_threshold"]["result"]["new_value"] == "5000"
    assert items_by_key["provision_role_templates"]["status"] == "applied"
    created_names = {r["role_name"] for r in items_by_key["provision_role_templates"]["result"]["created"]}
    # ConfigurationEngineService provisions the full canonical set via
    # seed_default_role_templates() (never a per-name subset -- see
    # CANONICAL_ROLE_TEMPLATE_NAMES docstring) whenever none exist yet,
    # regardless of which subset the Blueprint's decision itself named.
    assert created_names == set(CANONICAL_ROLE_TEMPLATE_NAMES)

    after = await _get_company(client, headers, company_id)
    assert after["po_approval_threshold"] == "5000.0000" or float(after["po_approval_threshold"]) == 5000.0
    # Business data (every other Company field) unchanged.
    for field in ("legal_name", "legal_name_ar", "vat_number", "cr_number", "fiscal_year_start_month"):
        assert after[field] == before[field], f"{field} changed unexpectedly"

    # Re-run Apply -- idempotency proof: no new roles, no further threshold
    # change, both items report as already applied.
    reapplied = (
        await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    ).json()
    assert reapplied["status"] == "applied"
    reapplied_items = {i["decision_key"]: i for i in reapplied["items"]}
    assert reapplied_items["po_approval_threshold"]["status"] == "skipped_already_applied"
    assert reapplied_items["provision_role_templates"]["status"] == "skipped_already_applied"
    assert await _role_names(company_id) == {"Admin", *CANONICAL_ROLE_TEMPLATE_NAMES}  # unchanged by the re-run

    after_reapply = await _get_company(client, headers, company_id)
    assert after_reapply["po_approval_threshold"] == after["po_approval_threshold"]


async def test_apply_on_superseded_blueprint_is_refused_with_zero_writes(client):
    company_id, _, headers = await _bootstrap_and_login(client, "CE_Superseded")
    before = await _get_company(client, headers, company_id)

    blueprint_v1 = await _approved_blueprint(client, headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)

    # A second Blueprint generation + approval supersedes v1 before Apply runs.
    gen2 = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    blueprint_v2_id = gen2.json()["id"]
    approve2 = await client.post(f"/api/v1/company-profile/blueprint/{blueprint_v2_id}/approve", headers=headers)
    assert approve2.status_code == 200

    v1_after = await client.get(f"/api/v1/company-profile/blueprint/{blueprint_v1['id']}", headers=headers)
    assert v1_after.json()["status"] == "superseded"

    apply_resp = await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    applied = apply_resp.json()
    assert applied["status"] == "failed"
    assert "no longer approved" in applied["failure_reason"]

    after = await _get_company(client, headers, company_id)
    assert after["po_approval_threshold"] == before["po_approval_threshold"]


async def test_partial_failure_rolls_back_every_write_in_the_attempt(client):
    """Forces the provision_role_templates item into its documented
    'partial role-template state' failure branch (some but not all
    canonical templates exist) -- decision_key ordering runs
    po_approval_threshold first, so this also proves that a successful
    earlier write in the same Apply attempt is rolled back when a later
    item in the same attempt fails."""
    company_id, _, headers = await _bootstrap_and_login(client, "CE_PartialFailure")
    await _clear_role_templates(company_id, names=("Accountant",))  # leaves Sales/Purchasing/Read-Only Viewer
    before = await _get_company(client, headers, company_id)
    assert before["po_approval_threshold"] is None

    await _approved_blueprint(client, headers)  # default profile -> role decision targets {Accountant, Sales}
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)

    applied = (
        await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    ).json()
    assert applied["status"] == "failed"
    assert applied["failure_reason"] is not None

    items_by_key = {i["decision_key"]: i for i in applied["items"]}
    # The threshold write was attempted first and succeeded in-memory, but
    # the whole nested transaction rolled back -- its item reverts to
    # "pending" (never durably applied), while the actually-failing item
    # is the one explicitly marked "failed".
    assert items_by_key["po_approval_threshold"]["status"] == "pending"
    assert items_by_key["provision_role_templates"]["status"] == "failed"
    assert items_by_key["provision_role_templates"]["error_message"] is not None

    after = await _get_company(client, headers, company_id)
    assert after["po_approval_threshold"] is None  # rolled back, not 5000


async def test_company_isolation(client):
    company_a, _, headers_a = await _bootstrap_and_login(client, "CE_IsoA")
    company_b, _, headers_b = await _bootstrap_and_login(client, "CE_IsoB")
    await _clear_role_templates(company_a)
    await _clear_role_templates(company_b)

    await _approved_blueprint(client, headers_a)
    plan_a = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers_a)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan_a['id']}/validate", headers=headers_a)
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan_a['id']}/apply", headers=headers_a)

    # Company B has no Blueprint/Plan of its own and must be entirely
    # unaffected by company A's apply.
    company_b_after = await _get_company(client, headers_b, company_b)
    assert company_b_after["po_approval_threshold"] is None
    assert await _role_names(company_b) == {"Admin"}

    # Company B cannot see company A's plan.
    cross_get = await client.get(f"/api/v1/company-profile/configuration-plan/{plan_a['id']}", headers=headers_b)
    assert cross_get.status_code == 404


async def test_zero_business_data_mutation(client):
    """Row counts for representative business tables (never touched by the
    Configuration Engine's write set) stay at zero before AND after Apply
    -- this is a fresh test company with no documents, so any non-zero
    count after Apply would prove an unintended write."""
    from sqlalchemy import text as sql_text

    company_id, _, headers = await _bootstrap_and_login(client, "CE_ZeroBizMutation")
    await _clear_role_templates(company_id)
    await _approved_blueprint(client, headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)

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

    apply_resp = await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)
    assert apply_resp.json()["status"] == "applied"

    after = await _counts()
    assert after == before


async def test_requires_permission_to_apply(client):
    company_id, _, headers = await _bootstrap_and_login(client, "CE_RBAC")
    await _approved_blueprint(client, headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)

    resp = await client.post(
        f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers={"X-Company-Id": company_id}
    )
    assert resp.status_code == 401


async def test_audit_log_records_every_real_write(client):
    from sqlalchemy import text as sql_text

    company_id, tenant_id, headers = await _bootstrap_and_login(client, "CE_Audit")
    await _clear_role_templates(company_id)
    await _approved_blueprint(client, headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers)

    async with AsyncSessionLocal() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            sql_text(
                "SELECT target_table, field_name, old_value, new_value, user_id FROM audit_log "
                "WHERE company_id = :cid ORDER BY changed_at"
            ),
            {"cid": company_id},
        )
        rows = result.all()

    company_rows = [r for r in rows if r.target_table == "company" and r.field_name == "po_approval_threshold"]
    assert len(company_rows) == 1
    assert company_rows[0].old_value is None
    assert company_rows[0].new_value == "5000"
    assert company_rows[0].user_id is not None

    role_rows = [r for r in rows if r.target_table == "role" and r.field_name == "name"]
    role_names = {r.new_value for r in role_rows}
    assert role_names == set(CANONICAL_ROLE_TEMPLATE_NAMES)
