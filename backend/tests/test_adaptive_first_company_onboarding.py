"""Adaptive ERP -- Stage 2.5 closure: First-Company Entry Integration.

The Stage 2.5 real-user-journey diagnostic found that a brand-new
customer's very first company (created via /setup -> POST /identity/
bootstrap) never reached the Adaptive wizard: bootstrap mints no session,
and the wizard's own Step 0 ("Create Company") assumes an *existing*
active company, so it cannot be the entry point for a first company at
all. The fix is frontend-only orchestration (frontend/app/(auth)/setup/
page.tsx now auto-logs-in after a successful bootstrap and redirects into
/company-setup?mode=first, which skips the wizard's own redundant Step 0)
-- no backend route, schema, model, or business logic changed.

This file proves the underlying API sequence that orchestration drives is
sound: bootstrap -> login -> Customer Profile -> Sizing -> Blueprint ->
Approve -> Configuration Plan -> Validate -> Apply, run directly against
the company bootstrap() itself created (never a second, separately
created company, unlike test_adaptive_vertical_slice.py's "add another
company" story) and without any /auth/refresh call -- a fresh /auth/login
token already carries the new company_id in authorized_companies
(AuthenticationService.issue_tokens() derives it live from the DB), so
that step, needed for the *second*-company path, does not exist here.
"""

from sqlalchemy import delete, select
from sqlalchemy import text as sql_text

from src.modules.identity.infrastructure.models import Role, RolePermission
from src.shared.infrastructure.db.session import (
    AsyncSessionLocal,
    set_company_context,
    set_tenant_context,
)
from src.shared.security.jwt import decode_token
from tests.conftest import unique_email, unique_vat

CANONICAL_ROLE_TEMPLATE_NAMES = ("Accountant", "Sales", "Purchasing & Warehouse", "Read-Only Viewer")


async def _bootstrap_first_company(client, label="FC"):
    """Mirrors exactly what /setup's new success handler does for a
    brand-new customer: bootstrap, then an immediate /auth/login with the
    same credentials just submitted -- never /auth/refresh (see module
    docstring). Returns the credentials too, so tests can log in again
    independently to simulate a *returning* user."""
    payload = {
        "tenant_legal_name": f"{label} Holding",
        "company_legal_name": f"{label} Co.",
        "company_legal_name_ar": f"{label} Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": f"{label} Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201, boot_resp.text
    boot_body = boot_resp.json()
    tenant_id = boot_body["tenant_id"]
    company_id = boot_body["company_id"]
    branch_id = boot_body["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    assert login_resp.status_code == 200, login_resp.text
    body = login_resp.json()
    assert "requires_2fa" not in body, "a freshly bootstrapped admin must never be challenged for 2FA"
    token = body["access_token"]

    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "branch_id": branch_id,
        "token": token,
        "headers": headers,
        "payload": payload,
    }


async def _clear_role_templates(company_id: str, names=CANONICAL_ROLE_TEMPLATE_NAMES) -> None:
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


async def _run_onboarding_to_apply(client, headers):
    """Runs Customer Profile -> Sizing -> Blueprint -> Approve ->
    Configuration Plan -> Validate -> Apply, exactly the sequence the
    wizard drives once it lands on step 1 (mode=first). Returns the final
    apply response."""
    profile_resp = await client.post(
        "/api/v1/company-profile",
        headers=headers,
        json={"industry": "Retail", "employee_count": 8, "branch_count": 1, "approval_rigor_preference": "low"},
    )
    assert profile_resp.status_code == 201, profile_resp.text

    sizing_resp = await client.post("/api/v1/company-profile/sizing", headers=headers)
    assert sizing_resp.status_code == 201, sizing_resp.text

    blueprint_resp = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    assert blueprint_resp.status_code == 201, blueprint_resp.text
    blueprint = blueprint_resp.json()
    assert blueprint["status"] == "draft"

    approve_resp = await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=headers)
    assert approve_resp.status_code == 200, approve_resp.text

    plan_resp = await client.post("/api/v1/company-profile/configuration-plan", headers=headers)
    assert plan_resp.status_code == 201, plan_resp.text
    plan = plan_resp.json()

    validate_resp = await client.post(
        f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers
    )
    assert validate_resp.status_code == 200, validate_resp.text
    assert validate_resp.json()["status"] == "validated"

    apply_resp = await client.post(
        f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers
    )
    assert apply_resp.status_code == 200, apply_resp.text
    return apply_resp.json()


# --- Test 1: First-company journey ------------------------------------------


async def test_first_company_journey_bootstrap_to_apply(client):
    """A brand-new customer's very first company: bootstrap -> login ->
    the full Adaptive chain, driven against the SAME company bootstrap()
    created -- no second company, no /company-setup Step 0 involved."""
    ctx = await _bootstrap_first_company(client, "FC_Happy")
    await _clear_role_templates(ctx["company_id"])

    applied = await _run_onboarding_to_apply(client, ctx["headers"])
    assert applied["status"] == "applied"
    applied_items = {i["decision_key"]: i for i in applied["items"]}
    assert applied_items["po_approval_threshold"]["status"] == "applied"
    assert applied_items["provision_role_templates"]["status"] == "applied"

    after_company = await _get_company(client, ctx["headers"], ctx["company_id"])
    assert after_company["po_approval_threshold"] is not None
    assert await _role_names(ctx["company_id"]) == {"Admin", *CANONICAL_ROLE_TEMPLATE_NAMES}


# --- Test 2: Existing company user is never forced into onboarding ---------


async def test_existing_company_user_not_forced_into_onboarding(client):
    """A returning user with an already-onboarded company: an independent,
    later /auth/login (simulating a fresh browser session, exactly what
    the untouched /login page still does) returns a normal TokenResponse
    with no new fields, and never implicitly creates a Customer Profile --
    the redirect into Adaptive onboarding lives entirely in /setup's own
    success handler, which a returning user never goes through again."""
    ctx = await _bootstrap_first_company(client, "FC_Existing")

    # Returning user: a second, independent login (not the one done at
    # bootstrap time) -- the exact call /login/page.tsx already makes.
    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": ctx["payload"]["admin_email"], "password": ctx["payload"]["admin_password"]},
    )
    assert login_resp.status_code == 200, login_resp.text
    body = login_resp.json()
    assert set(body.keys()) == {"access_token", "refresh_token", "token_type"}, (
        "login response shape must be unchanged for a returning user"
    )

    # Login alone -- with zero calls into company-profile -- must not have
    # silently provisioned a profile for this company.
    headers = {"Authorization": f"Bearer {body['access_token']}", "X-Company-Id": ctx["company_id"]}
    profile_resp = await client.get("/api/v1/company-profile", headers=headers)
    assert profile_resp.status_code == 404


# --- Test 3: Multiple companies -- selection behavior unaffected -----------


async def test_multiple_companies_authorized_list_unaffected(client):
    """A user who goes on to have more than one company (the existing "add
    another company" path, Stage 2.4/2.5's own POST /companies) still gets
    both companies back in authorized_companies on a fresh login -- the
    signal /login/page.tsx uses to route to /select-company instead of
    /dashboard. This integration adds no branching that could change that
    count."""
    ctx = await _bootstrap_first_company(client, "FC_Multi")

    create_resp = await client.post(
        "/api/v1/identity/companies",
        headers=ctx["headers"],
        json={
            "legal_name": "FC_Multi Second Co.",
            "legal_name_ar": "FC_Multi Second Arabic",
            "vat_number": unique_vat(),
            "base_currency_code": "SAR",
            "valuation_method": "average",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    second_company_id = create_resp.json()["id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": ctx["payload"]["admin_email"], "password": ctx["payload"]["admin_password"]},
    )
    assert login_resp.status_code == 200, login_resp.text
    payload = decode_token(login_resp.json()["access_token"])
    authorized = payload.get("authorized_companies", [])
    authorized_company_ids = {entry.split(":")[0] for entry in authorized}
    assert authorized_company_ids == {ctx["company_id"], second_company_id}


# --- Test 4: Authorization refresh is not needed after bootstrap+login -----


async def test_authorization_context_correct_without_refresh(client):
    """The access token minted by the login that immediately follows
    bootstrap already carries the new company_id in authorized_companies
    (issue_tokens() derives it live from the DB, unlike the JWT baked at
    an earlier issue time) -- proving /auth/refresh genuinely has no role
    in this flow, unlike the wizard's own Step 0 ("add another company")."""
    ctx = await _bootstrap_first_company(client, "FC_Auth")

    payload = decode_token(ctx["token"])
    authorized = payload.get("authorized_companies", [])
    assert any(
        entry == ctx["company_id"] or entry.startswith(f"{ctx['company_id']}:") for entry in authorized
    ), "the first login's own token must already authorize the bootstrapped company"

    # And a company-profile call succeeds on the very first attempt.
    resp = await client.post("/api/v1/company-profile", headers=ctx["headers"], json={})
    assert resp.status_code == 201, resp.text


# --- Test 5: Zero unintended business-data mutation -------------------------


async def test_first_company_onboarding_zero_business_data_mutation(client):
    """The first-company onboarding chain touches no business tables."""
    ctx = await _bootstrap_first_company(client, "FC_ZeroBiz")
    await _clear_role_templates(ctx["company_id"])
    company_id = ctx["company_id"]

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

    applied = await _run_onboarding_to_apply(client, ctx["headers"])
    assert applied["status"] == "applied"

    after = await _counts()
    assert after == before


# --- Test 6: Idempotency -----------------------------------------------------


async def test_first_company_onboarding_apply_idempotent(client):
    """Re-applying the same Configuration Plan for a bootstrap-created
    first company creates no duplicate roles and no further audit-visible
    change -- both items simply report as already applied."""
    ctx = await _bootstrap_first_company(client, "FC_Idempotent")
    await _clear_role_templates(ctx["company_id"])
    headers = ctx["headers"]

    await client.post("/api/v1/company-profile", headers=headers, json={})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/configuration-plan/{plan['id']}/validate", headers=headers)

    first_apply = await client.post(
        f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers
    )
    assert first_apply.json()["status"] == "applied"
    roles_after_first = await _role_names(ctx["company_id"])

    second_apply = await client.post(
        f"/api/v1/company-profile/configuration-plan/{plan['id']}/apply", headers=headers
    )
    assert second_apply.status_code == 200, second_apply.text
    reapplied_items = {i["decision_key"]: i for i in second_apply.json()["items"]}
    assert reapplied_items["po_approval_threshold"]["status"] == "skipped_already_applied"
    assert reapplied_items["provision_role_templates"]["status"] == "skipped_already_applied"
    assert await _role_names(ctx["company_id"]) == roles_after_first

    async with AsyncSessionLocal() as session:
        await set_tenant_context(session, ctx["tenant_id"])
        result = await session.execute(
            sql_text(
                "SELECT COUNT(*) FROM audit_log WHERE company_id = :cid "
                "AND target_table = 'company' AND field_name = 'po_approval_threshold'"
            ),
            {"cid": ctx["company_id"]},
        )
        assert result.scalar_one() == 1, "idempotent re-apply must not write a second audit entry"
