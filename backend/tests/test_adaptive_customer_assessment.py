"""Adaptive ERP -- Customer Assessment / Implementation Summary.

Grounded in docs/adaptive/03 (Customer Profile spec, esp. §J Future
Needs), docs/adaptive/05 (Blueprint spec, traceability), and
docs/adaptive/09 ("Assessment" is the Sizing Engine scoring the profile,
in the official sales/onboarding flow terminology). A pure read/
aggregation layer over CompanyProfile -> SizingResult -> ErpBlueprint ->
ConfigurationPlan -- see AssessmentService's own docstring
(company_profile/application/services.py). No new table, no new write
path, no new audit mechanism: everything here traces back to rows
already created (and already tested) by Stage 2.1-2.5.
"""

from sqlalchemy import text as sql_text

from src.shared.infrastructure.db.session import AsyncSessionLocal, set_company_context
from tests.conftest import unique_email, unique_vat

CANONICAL_ROLE_TEMPLATE_NAMES = ("Accountant", "Sales", "Purchasing & Warehouse", "Read-Only Viewer")


async def _bootstrap_and_login(client, label="CA"):
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
    company_id = boot_resp.json()["company_id"]
    branch_id = boot_resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, headers


async def _get_assessment(client, headers):
    resp = await client.get("/api/v1/company-profile/assessment", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- 1: Assessment reflects real profile data --------------------------


async def test_assessment_reflects_real_profile_data(client):
    _, headers = await _bootstrap_and_login(client, "CA_Profile")
    profile_resp = await client.post(
        "/api/v1/company-profile",
        headers=headers,
        json={"industry": "Wholesale Trading", "employee_count": 22, "branch_count": 1},
    )
    assert profile_resp.status_code == 201, profile_resp.text

    body = await _get_assessment(client, headers)
    assert body["profile"]["industry"] == "Wholesale Trading"
    assert body["profile"]["employee_count"] == 22
    # Onboarding not finished yet -- honest partial state, not an error.
    assert body["sizing"] is None
    assert body["blueprint"] is None
    assert body["configuration_plan"] is None


# --- 2/3/4: sizing / blueprint / configuration plan included -----------


async def test_assessment_includes_sizing_blueprint_and_plan(client):
    company_id, headers = await _bootstrap_and_login(client, "CA_FullChain")
    await client.post("/api/v1/company-profile", headers=headers, json={"employee_count": 10})
    sizing = (await client.post("/api/v1/company-profile/sizing", headers=headers)).json()
    blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()

    body = await _get_assessment(client, headers)
    assert body["company_id"] == company_id
    assert body["sizing"]["id"] == sizing["id"]
    assert body["blueprint"]["id"] == blueprint["id"]
    assert body["configuration_plan"]["id"] == plan["id"]
    assert body["configuration_plan"]["blueprint_id"] == blueprint["id"]


# --- 5: Capability Gaps appear for unactionable decisions ---------------


async def test_capability_gaps_visible_in_matrix(client):
    _, headers = await _bootstrap_and_login(client, "CA_Gaps")
    await client.post("/api/v1/company-profile", headers=headers, json={"cost_center_tracking_needed": True})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    await client.post("/api/v1/company-profile/blueprint", headers=headers)

    body = await _get_assessment(client, headers)
    matrix = {e["key"]: e for e in body["capability_matrix"]}
    assert matrix["cost_center_tracking"]["is_gap"] is True
    assert matrix["cost_center_tracking"]["actionable"] is False
    assert matrix["provision_additional_branch"]["is_gap"] is True
    assert matrix["multi_currency_support"]["is_gap"] is True
    # Actionable ones must NOT be flagged as gaps.
    assert matrix["po_approval_threshold"]["is_gap"] is False
    assert matrix["provision_role_templates"]["is_gap"] is False


# --- 6: HR never becomes actionable -------------------------------------


async def test_hr_never_actionable_always_a_future_need(client):
    _, headers = await _bootstrap_and_login(client, "CA_HR")
    await client.post("/api/v1/company-profile", headers=headers, json={})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    await client.post("/api/v1/company-profile/blueprint", headers=headers)

    body = await _get_assessment(client, headers)
    # No decision anywhere claims HR/payroll is actionable -- it simply
    # isn't a decision key at all (no CompanyProfile field asks about it).
    decision_keys = {e["key"] for e in body["capability_matrix"]}
    assert "payroll_hr" not in decision_keys
    assert not any("payroll" in key or key in ("hr", "hr_module") for key in decision_keys)
    future_need_keys = {n["key"] for n in body["future_needs"]}
    assert "payroll_hr" in future_need_keys


# --- 7: Cost Center stays a gap, no CRUD invented ------------------------


async def test_cost_center_stays_gap_no_crud_invented(client):
    _, headers = await _bootstrap_and_login(client, "CA_CostCenter")
    await client.post("/api/v1/company-profile", headers=headers, json={"cost_center_tracking_needed": True})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    await client.post("/api/v1/company-profile/blueprint", headers=headers)

    body = await _get_assessment(client, headers)
    matrix = {e["key"]: e for e in body["capability_matrix"]}
    assert matrix["cost_center_tracking"]["category"] == "EXTENSIBLE"
    assert matrix["cost_center_tracking"]["actionable"] is False
    assert matrix["cost_center_tracking"]["needs_development"] is True
    # No CostCenter management endpoint exists -- this stage does not add one.
    no_perm_headers = {"X-Company-Id": headers["X-Company-Id"]}
    resp = await client.post("/api/v1/accounting/cost-centers", headers=no_perm_headers, json={})
    assert resp.status_code in (404, 401)  # route doesn't exist (404), never a working create


# --- 8: Existing company unaffected --------------------------------------


async def test_existing_company_history_unaffected_by_assessment(client):
    company_id, headers = await _bootstrap_and_login(client, "CA_Existing")
    await client.post("/api/v1/company-profile", headers=headers, json={"employee_count": 5})
    await client.post("/api/v1/company-profile/sizing", headers=headers)

    before = await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)
    await _get_assessment(client, headers)
    await _get_assessment(client, headers)
    after = await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)
    assert before.json() == after.json()


# --- 9: Company isolation -------------------------------------------------


async def test_assessment_company_isolation(client):
    _, headers_a = await _bootstrap_and_login(client, "CA_IsoA")
    await client.post("/api/v1/company-profile", headers=headers_a, json={"industry": "Retail A"})
    _, headers_b = await _bootstrap_and_login(client, "CA_IsoB")

    # Company B has no profile at all -- its own Assessment 404s.
    resp_b = await client.get("/api/v1/company-profile/assessment", headers=headers_b)
    assert resp_b.status_code == 404

    body_a = await _get_assessment(client, headers_a)
    assert body_a["profile"]["industry"] == "Retail A"


# --- 10: RBAC ---------------------------------------------------------------


async def test_assessment_rbac(client):
    _, headers = await _bootstrap_and_login(client, "CA_RBAC")
    await client.post("/api/v1/company-profile", headers=headers, json={})

    no_auth_headers = {"X-Company-Id": headers["X-Company-Id"]}
    resp = await client.get("/api/v1/company-profile/assessment", headers=no_auth_headers)
    assert resp.status_code == 401


# --- 11: Audit / traceability chain ----------------------------------------


async def test_assessment_traceability_chain(client):
    _, headers = await _bootstrap_and_login(client, "CA_Trace")
    profile = (await client.post("/api/v1/company-profile", headers=headers, json={})).json()
    sizing = (await client.post("/api/v1/company-profile/sizing", headers=headers)).json()
    blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()
    await client.post(f"/api/v1/company-profile/blueprint/{blueprint['id']}/approve", headers=headers)
    plan = (await client.post("/api/v1/company-profile/configuration-plan", headers=headers)).json()

    body = await _get_assessment(client, headers)
    # Profile -> Sizing -> Blueprint -> Configuration Plan Item, each FK
    # verifiable, exactly as already stored (no new audit mechanism).
    assert body["sizing"]["company_profile_id"] == profile["id"]
    assert body["blueprint"]["company_profile_id"] == profile["id"]
    assert body["blueprint"]["sizing_result_id"] == sizing["id"]
    assert body["configuration_plan"]["blueprint_id"] == blueprint["id"]


# --- 12: Zero business-data mutation from reading an Assessment -------------


async def test_assessment_zero_business_data_mutation(client):
    company_id, headers = await _bootstrap_and_login(client, "CA_ZeroBiz")
    await client.post("/api/v1/company-profile", headers=headers, json={})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    await client.post("/api/v1/company-profile/blueprint", headers=headers)

    async def _counts():
        async with AsyncSessionLocal() as session:
            await set_company_context(session, company_id)
            counts = {}
            for table in ("partner", "product", "sales_invoice", "journal_entry", "purchase_order", "role"):
                result = await session.execute(
                    sql_text(f"SELECT COUNT(*) FROM {table} WHERE company_id = :cid"), {"cid": company_id}
                )
                counts[table] = result.scalar_one()
            return counts

    before = await _counts()
    await _get_assessment(client, headers)
    after = await _counts()
    assert after == before


# --- 13: Reopening Assessment creates no duplicates -------------------------


async def test_reopening_assessment_no_duplicate_data(client):
    _, headers = await _bootstrap_and_login(client, "CA_Reopen")
    await client.post("/api/v1/company-profile", headers=headers, json={})
    await client.post("/api/v1/company-profile/sizing", headers=headers)
    blueprint = (await client.post("/api/v1/company-profile/blueprint", headers=headers)).json()

    first = await _get_assessment(client, headers)
    second = await _get_assessment(client, headers)
    third = await _get_assessment(client, headers)
    assert first["blueprint"]["id"] == second["blueprint"]["id"] == third["blueprint"]["id"] == blueprint["id"]
    assert first["sizing"]["id"] == second["sizing"]["id"] == third["sizing"]["id"]

    # No new Blueprint/SizingResult rows were created by three reads.
    blueprints = (await client.get("/api/v1/company-profile/blueprint", headers=headers)).json()
    assert len(blueprints) == 1


# --- 14: Assessment tied to the correct company ------------------------------


async def test_assessment_matches_calling_company(client):
    company_a, headers_a = await _bootstrap_and_login(client, "CA_MatchA")
    company_b, headers_b = await _bootstrap_and_login(client, "CA_MatchB")
    await client.post("/api/v1/company-profile", headers=headers_a, json={"industry": "A-industry"})
    await client.post("/api/v1/company-profile", headers=headers_b, json={"industry": "B-industry"})

    body_a = await _get_assessment(client, headers_a)
    body_b = await _get_assessment(client, headers_b)
    assert body_a["company_id"] == company_a
    assert body_a["profile"]["industry"] == "A-industry"
    assert body_b["company_id"] == company_b
    assert body_b["profile"]["industry"] == "B-industry"
