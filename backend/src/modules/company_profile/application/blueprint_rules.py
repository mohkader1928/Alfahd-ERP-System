"""ERP Blueprint decision generation (Adaptive ERP Stage 2.3).

docs/adaptive/05-erp-blueprint-spec.md. Pure function of (profile values,
sizing dimension scores, thresholds) -- deterministic, same inputs always
produce the same decisions (docs/adaptive/12 Principle 10). Thresholds
come from the active SizingRuleSet.rules["blueprint_decisions"] JSONB,
never hardcoded here (docs/adaptive/06 §6.4).

Every decision is honestly tagged `actionable` per
docs/adaptive/10-adaptive-gap-analysis.md: only decisions the
Configuration Engine can actually apply today (using an existing, real
Core write path) are actionable=True. Everything else is a real,
correctly-reasoned recommendation the Core has no management surface for
yet -- recorded, never silently applied or silently dropped.
"""

from typing import Any

from src.modules.company_profile.domain.entities import BlueprintDecision

EDITION_BANDS = [
    (30, "Micro"),
    (50, "Small"),
    (70, "SME"),
    (85, "Mid-Market"),
]
EDITION_TOP = "Growth"


def _recommended_edition(average_score: float) -> str:
    for ceiling, name in EDITION_BANDS:
        if average_score < ceiling:
            return name
    return EDITION_TOP


def generate_decisions(
    profile: dict[str, Any], dimension_scores: dict[str, dict[str, Any]], thresholds: dict[str, Any]
) -> tuple[list[BlueprintDecision], dict[str, bool]]:
    """Returns (decisions, enabled_modules). enabled_modules is a plain
    dict of module-key -> bool -- a *recommendation* record only; the
    Golden Core's module activation remains the global ENABLED_MODULES
    list (docs/adaptive/02 §2.7) until a later stage builds real
    per-company module gating. Nothing here disables a module that's
    already running for anyone."""
    decisions: list[BlueprintDecision] = []

    # STANDARD -- always true today, recorded for completeness/explainability.
    decisions.append(
        BlueprintDecision(
            key="enable_accounting_module",
            category="STANDARD",
            decision=True,
            reason="Accounting is core to every company in the Golden Core; not optional.",
            actionable=False,
        )
    )
    decisions.append(
        BlueprintDecision(
            key="enable_sales_module",
            category="STANDARD",
            decision=True,
            reason="Sales is core to every company in the Golden Core; not optional.",
            actionable=False,
        )
    )

    # CONFIGURABLE -- module visibility (recommendation only; see docstring).
    enable_inventory = not bool(profile.get("is_service_business"))
    decisions.append(
        BlueprintDecision(
            key="enable_inventory_module",
            category="CONFIGURABLE",
            decision=enable_inventory,
            reason=f"is_service_business={profile.get('is_service_business')}",
            actionable=False,
        )
    )
    enable_fixed_assets = bool(profile.get("owns_fixed_assets"))
    decisions.append(
        BlueprintDecision(
            key="enable_fixed_assets_module",
            category="CONFIGURABLE",
            decision=enable_fixed_assets,
            reason=f"owns_fixed_assets={profile.get('owns_fixed_assets')}",
            actionable=False,
        )
    )

    # CONFIGURABLE, actionable -- PO approval threshold. Company.po_approval_threshold
    # already exists and is already the one real approval knob in the Core
    # (docs/adaptive/02 §2.4) -- the Configuration Engine can genuinely set it.
    rigor = profile.get("approval_rigor_preference", "low")
    threshold_amounts = thresholds.get("approval_threshold_amounts", {})
    approval_value = threshold_amounts.get(rigor)
    decisions.append(
        BlueprintDecision(
            key="po_approval_threshold",
            category="CONFIGURABLE",
            decision=approval_value,
            reason=f"approval_rigor_preference={rigor!r} maps to threshold_amounts[{rigor!r}]={approval_value!r}",
            actionable=True,
        )
    )

    # CONFIGURABLE, actionable -- role templates. seed_default_role_templates()
    # already exists (docs/adaptive/02 §2.4) -- genuinely actionable.
    org_score = dimension_scores["organizational_complexity"]["score"]
    role_templates = ["Accountant", "Sales"]
    if enable_inventory or profile.get("monthly_purchase_order_volume"):
        role_templates.append("Purchasing & Warehouse")
    viewer_threshold = thresholds.get("security_high_role_threshold", 50)
    if org_score >= viewer_threshold:
        role_templates.append("Read-Only Viewer")
    decisions.append(
        BlueprintDecision(
            key="provision_role_templates",
            category="CONFIGURABLE",
            decision=role_templates,
            reason=f"organizational_complexity score={org_score} (threshold={viewer_threshold}); purchasing activity considered",
            actionable=True,
        )
    )

    # EXTENSIBLE -- cost center tracking. Table + JE-line wiring exist, but
    # no CRUD API/UI (docs/adaptive/10 gap analysis, P1) -- not actionable
    # until that gap closes.
    financial_score = dimension_scores["financial_complexity"]["score"]
    cost_center_threshold = thresholds.get("financial_complexity_cost_center_threshold", 50)
    want_cost_centers = bool(profile.get("cost_center_tracking_needed")) or financial_score >= cost_center_threshold
    decisions.append(
        BlueprintDecision(
            key="cost_center_tracking",
            category="EXTENSIBLE",
            decision=want_cost_centers,
            reason=(
                f"cost_center_tracking_needed={profile.get('cost_center_tracking_needed')}, "
                f"financial_complexity score={financial_score} (threshold={cost_center_threshold}) -- "
                "NOT actionable today: no CostCenter CRUD API/UI exists yet (see gap analysis)."
            ),
            actionable=False,
        )
    )

    # CONFIGURABLE, actionable -- additional branch provisioning.
    # POST /companies/{id}/branches already exists (docs/adaptive/02 §2.3),
    # so this is genuinely actionable, unlike cost centers above.
    branch_threshold = thresholds.get("organizational_complexity_branch_threshold", 60)
    recommend_second_branch = org_score >= branch_threshold and (profile.get("branch_count") or 1) <= 1
    decisions.append(
        BlueprintDecision(
            key="provision_additional_branch",
            category="CONFIGURABLE",
            decision=recommend_second_branch,
            reason=f"organizational_complexity score={org_score} (threshold={branch_threshold}), branch_count={profile.get('branch_count')!r}",
            actionable=True,
        )
    )

    # STANDARD -- informational edition label (docs/adaptive/07 §7.1: a
    # label over configuration state, never a code branch).
    avg_score = sum(d["score"] for d in dimension_scores.values()) / len(dimension_scores)
    edition = _recommended_edition(avg_score)
    decisions.append(
        BlueprintDecision(
            key="recommended_edition_label",
            category="STANDARD",
            decision=edition,
            reason=f"average dimension score={avg_score:.1f}",
            actionable=False,
        )
    )

    enabled_modules = {
        "accounting": True,
        "sales": True,
        "inventory": enable_inventory,
        "fixed_assets": enable_fixed_assets,
        "purchasing": True,
        "payments": True,
    }
    return decisions, enabled_modules
