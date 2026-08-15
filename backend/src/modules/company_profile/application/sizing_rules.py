"""Sizing Engine scoring (Adaptive ERP Stage 2.2).

docs/adaptive/04-erp-sizing-engine-spec.md §4.3: "every weight and every
threshold... must live in a versioned configuration record, never as a
magic number inside application service code." This module is the
scoring *mechanism* (code, per §6.4 of docs/adaptive/06) — it reads all
its numeric thresholds from the `rules` argument (the active
`SizingRuleSet.rules` JSONB, never a hardcoded constant used at scoring
time). `DEFAULT_SIZING_RULES` below exists only as the literal seed data
for rule_version "sizing-rules-v1" (see the Stage 2.2 migration) — once
seeded, the engine only ever reads the DB row, never this constant.

Deterministic by construction: a pure function of (profile values, rules)
with no I/O, no randomness, no clock reads — the same two inputs always
produce the same output (docs/adaptive/12 Principle 10).
"""

from typing import Any

from src.modules.company_profile.domain.entities import DimensionScore

DEFAULT_SIZING_RULES: dict[str, Any] = {
    "organizational_complexity": {
        "employee_bands": [10, 30, 100],
        "branch_bands": [1, 3, 10],
        "cost_center_bonus": 15,
    },
    "transaction_volume": {
        "sales_order_bands": [50, 200, 1000],
        "purchase_order_bands": [50, 200, 1000],
        "sku_bands": [50, 300, 2000],
    },
    "inventory_complexity": {
        "warehouse_bands": [1, 3, 10],
        "service_business_score": 10,
    },
    "financial_complexity": {
        "coa_depth_weight": 20,
        "cost_center_bonus": 20,
        "multi_currency_bonus": 30,
    },
    "tax_compliance_complexity": {
        "base_score": 20,
        "withholding_bonus": 40,
    },
    "asset_complexity": {
        "owns_assets_base": 30,
        "asset_count_bands": [5, 20, 100],
    },
    "approval_governance_complexity": {
        "low": 20,
        "medium": 55,
        "high": 90,
    },
    "security_access_complexity": {
        "user_bands": [5, 20, 100],
        "two_factor_bonus": 15,
    },
}


def _band_score(value: int | None, bands: list[int]) -> int:
    """Maps a raw count to a 0/25/50/75/100 band score against three
    ascending thresholds. `value is None` (the customer didn't answer)
    scores 0 — an unanswered question is never treated as "high
    complexity" by default."""
    if value is None:
        return 0
    low, mid, high = bands
    if value <= low:
        return 25
    if value <= mid:
        return 50
    if value <= high:
        return 75
    return 100


def _clamp(score: float) -> int:
    return max(0, min(100, round(score)))


def score_profile(profile: dict[str, Any], rules: dict[str, Any]) -> dict[str, DimensionScore]:
    """profile: a plain dict of CompanyProfile field values (see
    docs/adaptive/03-customer-profile-spec.md). rules: the active
    SizingRuleSet.rules JSONB. Returns one DimensionScore per
    SIZING_DIMENSIONS entry — never partial, per SizingResult's own
    __post_init__ check."""
    r = rules
    out: dict[str, DimensionScore] = {}

    # Organizational Complexity
    oc = r["organizational_complexity"]
    emp_score = _band_score(profile.get("employee_count"), oc["employee_bands"])
    branch_score = _band_score(profile.get("branch_count"), oc["branch_bands"])
    bonus = oc["cost_center_bonus"] if profile.get("cost_center_tracking_needed") else 0
    score = _clamp(max(emp_score, branch_score) + bonus)
    out["organizational_complexity"] = DimensionScore(
        score=score,
        reason=(
            f"employee_count={profile.get('employee_count')!r} and "
            f"branch_count={profile.get('branch_count')!r} "
            f"(cost_center_tracking_needed={profile.get('cost_center_tracking_needed')})"
        ),
    )

    # Transaction Volume
    tv = r["transaction_volume"]
    sales_score = _band_score(profile.get("monthly_sales_order_volume"), tv["sales_order_bands"])
    purchase_score = _band_score(profile.get("monthly_purchase_order_volume"), tv["purchase_order_bands"])
    sku_score = _band_score(profile.get("sku_count_estimate"), tv["sku_bands"])
    score = _clamp(max(sales_score, purchase_score, sku_score))
    out["transaction_volume"] = DimensionScore(
        score=score,
        reason=(
            f"monthly_sales_order_volume={profile.get('monthly_sales_order_volume')!r}, "
            f"monthly_purchase_order_volume={profile.get('monthly_purchase_order_volume')!r}, "
            f"sku_count_estimate={profile.get('sku_count_estimate')!r}"
        ),
    )

    # Inventory Complexity
    ic = r["inventory_complexity"]
    if profile.get("is_service_business"):
        score = ic["service_business_score"]
        reason = "is_service_business=True — inventory is not a relevant concern for this company"
    else:
        score = _band_score(profile.get("warehouse_count"), ic["warehouse_bands"])
        reason = f"warehouse_count={profile.get('warehouse_count')!r} (is_service_business=False)"
    out["inventory_complexity"] = DimensionScore(score=_clamp(score), reason=reason)

    # Financial Complexity
    fc = r["financial_complexity"]
    coa = profile.get("coa_depth_preference")
    coa_score = (coa / 4 * 100) if coa else 0
    bonus = fc["cost_center_bonus"] if profile.get("cost_center_tracking_needed") else 0
    bonus += fc["multi_currency_bonus"] if profile.get("multi_currency_requested") else 0
    score = _clamp(coa_score + bonus)
    out["financial_complexity"] = DimensionScore(
        score=score,
        reason=(
            f"coa_depth_preference={coa!r}, cost_center_tracking_needed="
            f"{profile.get('cost_center_tracking_needed')}, multi_currency_requested="
            f"{profile.get('multi_currency_requested')}"
        ),
    )

    # Tax/Compliance Complexity
    tc = r["tax_compliance_complexity"]
    score = tc["base_score"] + (tc["withholding_bonus"] if profile.get("withholding_tax_needed") else 0)
    out["tax_compliance_complexity"] = DimensionScore(
        score=_clamp(score),
        reason=f"withholding_tax_needed={profile.get('withholding_tax_needed')}",
    )

    # Asset Complexity
    ac = r["asset_complexity"]
    if profile.get("owns_fixed_assets"):
        score = ac["owns_assets_base"] + _band_score(
            profile.get("fixed_asset_count_estimate"), ac["asset_count_bands"]
        ) / 2
        reason = f"owns_fixed_assets=True, fixed_asset_count_estimate={profile.get('fixed_asset_count_estimate')!r}"
    else:
        score = 0
        reason = "owns_fixed_assets=False"
    out["asset_complexity"] = DimensionScore(score=_clamp(score), reason=reason)

    # Approval/Governance Complexity
    agc = r["approval_governance_complexity"]
    rigor = profile.get("approval_rigor_preference", "low")
    score = agc.get(rigor, agc["low"])
    out["approval_governance_complexity"] = DimensionScore(
        score=_clamp(score), reason=f"approval_rigor_preference={rigor!r}"
    )

    # Security/Access Complexity
    sac = r["security_access_complexity"]
    user_score = _band_score(profile.get("desired_user_count"), sac["user_bands"])
    bonus = sac["two_factor_bonus"] if profile.get("two_factor_required") else 0
    score = _clamp(user_score + bonus)
    out["security_access_complexity"] = DimensionScore(
        score=score,
        reason=(
            f"desired_user_count={profile.get('desired_user_count')!r}, "
            f"two_factor_required={profile.get('two_factor_required')}"
        ),
    )

    return out
