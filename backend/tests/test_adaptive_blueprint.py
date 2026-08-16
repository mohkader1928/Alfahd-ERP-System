"""Adaptive ERP Stage 2.3 — ERP Blueprint.

Grounded in docs/adaptive/05-erp-blueprint-spec.md. Versioning/supersession
(§5.3) and the honest actionable/category tagging (docs/adaptive/10 gap
analysis) are the two things this stage's governing instructions explicitly
asked to be proven.
"""

from tests.conftest import unique_email, unique_vat

DECISION_KEYS = {
    "enable_accounting_module",
    "enable_sales_module",
    "enable_inventory_module",
    "enable_fixed_assets_module",
    "po_approval_threshold",
    "provision_role_templates",
    "cost_center_tracking",
    "provision_additional_branch",
    "multi_currency_support",
    "recommended_edition_label",
}
ACTIONABLE_KEYS = {"po_approval_threshold", "provision_role_templates"}


async def _bootstrap_and_login(client, label="BP"):
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


async def _create_profile(client, headers, **overrides):
    resp = await client.post("/api/v1/company-profile", headers=headers, json=overrides)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _size(client, headers):
    resp = await client.post("/api/v1/company-profile/sizing", headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_generate_before_profile_exists_is_404(client):
    _, headers = await _bootstrap_and_login(client, "BP_NoProfile")
    resp = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    assert resp.status_code == 404


async def test_generate_before_sizing_exists_is_404(client):
    _, headers = await _bootstrap_and_login(client, "BP_NoSizing")
    await _create_profile(client, headers)
    resp = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    assert resp.status_code == 404


async def test_generate_returns_all_decisions_with_honest_tagging(client):
    _, headers = await _bootstrap_and_login(client, "BP_AllDecisions")
    await _create_profile(client, headers, employee_count=15)
    await _size(client, headers)
    resp = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["blueprint_version"] == 1
    assert body["approved_at"] is None
    assert body["approved_by"] is None

    decisions = {d["key"]: d for d in body["decisions"]}
    assert set(decisions.keys()) == DECISION_KEYS
    for key, decision in decisions.items():
        assert decision["category"] in ("STANDARD", "CONFIGURABLE", "EXTENSIBLE", "CUSTOM_DEVELOPMENT")
        assert len(decision["reason"]) > 0
        assert decision["actionable"] == (key in ACTIONABLE_KEYS)
    # cost_center_tracking is a real, correctly-reasoned recommendation
    # the Core has no CRUD API for yet -- never silently applied.
    assert decisions["cost_center_tracking"]["category"] == "EXTENSIBLE"
    assert decisions["cost_center_tracking"]["actionable"] is False
    # provision_additional_branch: downgraded in Stage 2.4 Design & Safety
    # Review -- the decision carries no branch name and branch creation
    # has no duplicate-guard or safe revert path, so it stays a capability
    # gap rather than a workaround (see blueprint_rules.py comment).
    assert decisions["provision_additional_branch"]["actionable"] is False
    # multi_currency_support: honesty gap (docs/adaptive/03 §D) -- no
    # exchange_rate concept exists anywhere in the Core, so this must never
    # be actionable regardless of what the customer answered.
    assert decisions["multi_currency_support"]["category"] == "CUSTOM_DEVELOPMENT"
    assert decisions["multi_currency_support"]["actionable"] is False


async def test_multi_currency_requested_still_stays_a_capability_gap(client):
    """A customer answering 'yes' to multi-currency must never make the
    decision look actionable -- the gap is in the Core, not the answer."""
    _, headers = await _bootstrap_and_login(client, "BP_MultiCurrency")
    await _create_profile(client, headers, multi_currency_requested=True)
    await _size(client, headers)
    resp = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    decisions = {d["key"]: d for d in resp.json()["decisions"]}
    assert decisions["multi_currency_support"]["decision"] is True
    assert decisions["multi_currency_support"]["actionable"] is False


async def test_po_approval_threshold_maps_from_rigor_preference(client):
    _, headers = await _bootstrap_and_login(client, "BP_Rigor")
    await _create_profile(client, headers, approval_rigor_preference="high")
    await _size(client, headers)
    resp = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    decisions = {d["key"]: d for d in resp.json()["decisions"]}
    assert decisions["po_approval_threshold"]["decision"] == 100000


async def test_generate_creates_new_versions_not_overwrites(client):
    _, headers = await _bootstrap_and_login(client, "BP_Versioning")
    await _create_profile(client, headers)
    await _size(client, headers)
    first = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    second = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    assert first.json()["blueprint_version"] == 1
    assert second.json()["blueprint_version"] == 2
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["status"] == "draft"
    assert second.json()["status"] == "draft"


async def test_approve_sets_status_and_approver(client):
    _, headers = await _bootstrap_and_login(client, "BP_Approve")
    await _create_profile(client, headers)
    await _size(client, headers)
    draft = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    blueprint_id = draft.json()["id"]

    resp = await client.post(f"/api/v1/company-profile/blueprint/{blueprint_id}/approve", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["approved_at"] is not None
    assert body["approved_by"] is not None


async def test_approve_non_draft_is_conflict(client):
    _, headers = await _bootstrap_and_login(client, "BP_DoubleApprove")
    await _create_profile(client, headers)
    await _size(client, headers)
    draft = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    blueprint_id = draft.json()["id"]
    await client.post(f"/api/v1/company-profile/blueprint/{blueprint_id}/approve", headers=headers)

    resp = await client.post(f"/api/v1/company-profile/blueprint/{blueprint_id}/approve", headers=headers)
    assert resp.status_code == 409


async def test_approving_new_blueprint_supersedes_old_approved_one(client):
    """docs/adaptive/05 §5.3 -- exactly one 'currently approved' Blueprint
    per company at a time; the old one is superseded, never deleted."""
    _, headers = await _bootstrap_and_login(client, "BP_Supersede")
    await _create_profile(client, headers)
    await _size(client, headers)
    first = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    first_id = first.json()["id"]
    await client.post(f"/api/v1/company-profile/blueprint/{first_id}/approve", headers=headers)

    second = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    second_id = second.json()["id"]
    approve_second = await client.post(f"/api/v1/company-profile/blueprint/{second_id}/approve", headers=headers)
    assert approve_second.json()["status"] == "approved"

    first_after = await client.get(f"/api/v1/company-profile/blueprint/{first_id}", headers=headers)
    assert first_after.json()["status"] == "superseded"
    assert first_after.json()["superseded_by_id"] == second_id


async def test_get_latest_returns_highest_version(client):
    _, headers = await _bootstrap_and_login(client, "BP_Latest")
    await _create_profile(client, headers)
    await _size(client, headers)
    await client.post("/api/v1/company-profile/blueprint", headers=headers)
    second = await client.post("/api/v1/company-profile/blueprint", headers=headers)

    latest = await client.get("/api/v1/company-profile/blueprint/latest", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["id"] == second.json()["id"]


async def test_list_returns_all_versions_descending(client):
    _, headers = await _bootstrap_and_login(client, "BP_List")
    await _create_profile(client, headers)
    await _size(client, headers)
    first = await client.post("/api/v1/company-profile/blueprint", headers=headers)
    second = await client.post("/api/v1/company-profile/blueprint", headers=headers)

    listing = await client.get("/api/v1/company-profile/blueprint", headers=headers)
    assert listing.status_code == 200
    ids = [b["id"] for b in listing.json()]
    assert ids == [second.json()["id"], first.json()["id"]]


async def test_get_unknown_blueprint_is_404(client):
    _, headers = await _bootstrap_and_login(client, "BP_Unknown")
    resp = await client.get(
        "/api/v1/company-profile/blueprint/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert resp.status_code == 404


async def test_requires_permission(client):
    company_id, _ = await _bootstrap_and_login(client, "BP_Perm")
    resp = await client.post("/api/v1/company-profile/blueprint", headers={"X-Company-Id": company_id})
    assert resp.status_code == 401


async def test_company_isolation(client):
    _, headers_a = await _bootstrap_and_login(client, "BP_IsoA")
    _, headers_b = await _bootstrap_and_login(client, "BP_IsoB")
    await _create_profile(client, headers_a)
    await _create_profile(client, headers_b)
    await _size(client, headers_a)
    await _size(client, headers_b)

    blueprint_a = await client.post("/api/v1/company-profile/blueprint", headers=headers_a)
    blueprint_id_a = blueprint_a.json()["id"]

    # Company B must never see Company A's Blueprint.
    cross_get = await client.get(f"/api/v1/company-profile/blueprint/{blueprint_id_a}", headers=headers_b)
    assert cross_get.status_code == 404

    listing_b = await client.get("/api/v1/company-profile/blueprint", headers=headers_b)
    assert listing_b.json() == []
