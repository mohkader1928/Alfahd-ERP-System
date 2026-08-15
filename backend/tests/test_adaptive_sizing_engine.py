"""Adaptive ERP Stage 2.2 — Sizing Engine.

Grounded in docs/adaptive/04-erp-sizing-engine-spec.md. Determinism
(§4.3/§4.4) and boundary-case coverage are the two things this stage's
governing instructions explicitly asked to be proven, not just claimed.
"""

from tests.conftest import unique_email, unique_vat

SIZING_DIMENSIONS = (
    "organizational_complexity",
    "transaction_volume",
    "inventory_complexity",
    "financial_complexity",
    "tax_compliance_complexity",
    "asset_complexity",
    "approval_governance_complexity",
    "security_access_complexity",
)


async def _bootstrap_and_login(client, label="SZ"):
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


async def test_compute_before_profile_exists_is_404(client):
    _, headers = await _bootstrap_and_login(client, "SZ_NoProfile")
    resp = await client.post("/api/v1/company-profile/sizing", headers=headers)
    assert resp.status_code == 404


async def test_compute_returns_all_dimensions_with_scores_and_reasons(client):
    _, headers = await _bootstrap_and_login(client, "SZ_AllDims")
    await _create_profile(client, headers, employee_count=15)
    resp = await client.post("/api/v1/company-profile/sizing", headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["rule_version"] == "sizing-rules-v1"
    assert set(body["dimension_scores"].keys()) == set(SIZING_DIMENSIONS)
    for dim in SIZING_DIMENSIONS:
        entry = body["dimension_scores"][dim]
        assert 0 <= entry["score"] <= 100
        assert len(entry["reason"]) > 0


async def test_determinism_same_profile_same_result(client):
    """docs/adaptive/04 §4.3/§4.4 and docs/adaptive/12 Principle 10 — the
    same profile against the same active rule_version must always produce
    identical dimension_scores, computed twice in a row here."""
    _, headers = await _bootstrap_and_login(client, "SZ_Determinism")
    await _create_profile(
        client,
        headers,
        employee_count=42,
        branch_count=2,
        monthly_sales_order_volume=180,
        owns_fixed_assets=True,
        fixed_asset_count_estimate=12,
        approval_rigor_preference="medium",
    )
    first = await client.post("/api/v1/company-profile/sizing", headers=headers)
    second = await client.post("/api/v1/company-profile/sizing", headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["dimension_scores"] == second.json()["dimension_scores"]
    assert first.json()["rule_version"] == second.json()["rule_version"]
    # Two distinct, immutable result rows — recomputation is never an
    # in-place overwrite (docs/adaptive/05 §5.3's versioning discipline
    # applies equally to sizing history).
    assert first.json()["id"] != second.json()["id"]


async def test_get_latest_returns_most_recent(client):
    _, headers = await _bootstrap_and_login(client, "SZ_Latest")
    await _create_profile(client, headers, employee_count=5)
    first = await client.post("/api/v1/company-profile/sizing", headers=headers)
    second = await client.post("/api/v1/company-profile/sizing", headers=headers)
    latest = await client.get("/api/v1/company-profile/sizing/latest", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["id"] == second.json()["id"] != first.json()["id"]


async def test_boundary_empty_profile_scores_correctly(client):
    """A profile created with no optional fields set at all — every
    dimension must score exactly the "nothing answered" baseline, never a
    default-to-high-complexity guess (docs/adaptive/04 §4.2's "an
    unanswered question is never treated as high complexity")."""
    _, headers = await _bootstrap_and_login(client, "SZ_Empty")
    await _create_profile(client, headers)
    resp = await client.post("/api/v1/company-profile/sizing", headers=headers)
    scores = resp.json()["dimension_scores"]
    assert scores["organizational_complexity"]["score"] == 0
    assert scores["transaction_volume"]["score"] == 0
    assert scores["inventory_complexity"]["score"] == 0
    assert scores["financial_complexity"]["score"] == 0
    assert scores["tax_compliance_complexity"]["score"] == 20  # base_score only
    assert scores["asset_complexity"]["score"] == 0
    assert scores["approval_governance_complexity"]["score"] == 20  # default "low"
    assert scores["security_access_complexity"]["score"] == 0


async def test_boundary_maximal_profile_scores_high(client):
    _, headers = await _bootstrap_and_login(client, "SZ_Max")
    await _create_profile(
        client,
        headers,
        employee_count=500,
        branch_count=20,
        cost_center_tracking_needed=True,
        is_service_business=False,
        warehouse_count=20,
        monthly_sales_order_volume=5000,
        monthly_purchase_order_volume=5000,
        sku_count_estimate=5000,
        coa_depth_preference=4,
        multi_currency_requested=True,
        withholding_tax_needed=True,
        owns_fixed_assets=True,
        fixed_asset_count_estimate=200,
        approval_rigor_preference="high",
        desired_user_count=200,
        two_factor_required=True,
    )
    resp = await client.post("/api/v1/company-profile/sizing", headers=headers)
    scores = resp.json()["dimension_scores"]
    assert scores["organizational_complexity"]["score"] == 100
    assert scores["transaction_volume"]["score"] == 100
    assert scores["inventory_complexity"]["score"] == 100
    assert scores["financial_complexity"]["score"] == 100
    assert scores["tax_compliance_complexity"]["score"] == 60  # base 20 + withholding 40
    assert scores["asset_complexity"]["score"] == 80  # 30 base + 100/2 band
    assert scores["approval_governance_complexity"]["score"] == 90
    assert scores["security_access_complexity"]["score"] == 100


async def test_boundary_exact_band_edges_organizational(client):
    """employee_count exactly at a band edge (10) scores the lower band;
    one above it (11) crosses into the next — proves the engine uses
    inclusive "<=" boundaries consistently, not an off-by-one guess."""
    _, headers = await _bootstrap_and_login(client, "SZ_BandEdge")
    await _create_profile(client, headers, employee_count=10)
    at_edge = await client.post("/api/v1/company-profile/sizing", headers=headers)
    assert at_edge.json()["dimension_scores"]["organizational_complexity"]["score"] == 25

    await client.patch("/api/v1/company-profile", headers=headers, json={"employee_count": 11})
    above_edge = await client.post("/api/v1/company-profile/sizing", headers=headers)
    assert above_edge.json()["dimension_scores"]["organizational_complexity"]["score"] == 50


async def test_service_business_skips_inventory_complexity(client):
    _, headers = await _bootstrap_and_login(client, "SZ_Service")
    await _create_profile(client, headers, is_service_business=True, warehouse_count=15)
    resp = await client.post("/api/v1/company-profile/sizing", headers=headers)
    entry = resp.json()["dimension_scores"]["inventory_complexity"]
    assert entry["score"] == 10  # service_business_score, warehouse_count ignored
    assert "is_service_business=True" in entry["reason"]


async def test_requires_permission(client):
    company_id, _ = await _bootstrap_and_login(client, "SZ_Perm")
    resp = await client.post("/api/v1/company-profile/sizing", headers={"X-Company-Id": company_id})
    assert resp.status_code == 401


async def test_company_isolation_sizing_results(client):
    _, headers_a = await _bootstrap_and_login(client, "SZ_IsoA")
    _, headers_b = await _bootstrap_and_login(client, "SZ_IsoB")
    await _create_profile(client, headers_a, employee_count=5)
    await _create_profile(client, headers_b, employee_count=500)

    result_a = await client.post("/api/v1/company-profile/sizing", headers=headers_a)
    result_b = await client.post("/api/v1/company-profile/sizing", headers=headers_b)
    assert result_a.json()["company_id"] != result_b.json()["company_id"]

    latest_a = await client.get("/api/v1/company-profile/sizing/latest", headers=headers_a)
    latest_b = await client.get("/api/v1/company-profile/sizing/latest", headers=headers_b)
    assert latest_a.json()["id"] == result_a.json()["id"]
    assert latest_b.json()["id"] == result_b.json()["id"]
    # employee_count=5 <= the first band edge (10) -> 25, not 0 (0 is
    # reserved for "unanswered" -- see test_boundary_empty_profile_scores_correctly).
    assert latest_a.json()["dimension_scores"]["organizational_complexity"]["score"] == 25
    assert latest_b.json()["dimension_scores"]["organizational_complexity"]["score"] == 100
