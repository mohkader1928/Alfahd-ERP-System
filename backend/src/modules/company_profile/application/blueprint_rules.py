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

# docs/adaptive/03-customer-profile-spec.md §J "Future Needs" -- static,
# never derived from a per-customer answer (no structured field for any of
# these exists in CompanyProfile; §J is deliberately asked about only via
# the freeform growth_notes text, not a boolean). Always surfaced on the
# Customer Assessment as known Core boundaries so a request for any of
# these is never silently implied as available -- this is exactly what §J
# says: "recorded for product-roadmap signal only, never claimed as
# available." Not BlueprintDecision rows (they carry no per-company
# decision value), consumed only by AssessmentService.
FUTURE_NEEDS_CATALOG = (
    {
        "key": "api_integration_access",
        "note": "No public partner API exists today beyond the internal REST API.",
    },
    {
        "key": "ecommerce_connection",
        "note": "No e-commerce channel integration exists.",
    },
    {
        "key": "payroll_hr",
        "note": "No HR/payroll module exists -- Partner.is_employee is master-data only, not an HR system.",
    },
    {
        "key": "manufacturing",
        "note": "No BOM/production module exists.",
    },
    {
        "key": "crm",
        "note": "No lead/opportunity tracking exists -- Partner is master data only.",
    },
)


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

    # CONFIGURABLE, NOT actionable (Stage 2.4 Design & Safety Review §2.3).
    # POST /companies/{id}/branches exists, but this decision as modeled is
    # boolean-only -- it carries no branch name/name_ar, so there is no
    # concrete input to actually call that endpoint with. Branch creation
    # also has zero duplicate-guard and no safe deletion path, so even a
    # named decision couldn't be safely auto-applied or reverted yet. A
    # real capability gap, not a workaround target -- stays informational
    # until a future stage extends the decision model with a name and a
    # safe apply/revert story.
    branch_threshold = thresholds.get("organizational_complexity_branch_threshold", 60)
    recommend_second_branch = org_score >= branch_threshold and (profile.get("branch_count") or 1) <= 1
    decisions.append(
        BlueprintDecision(
            key="provision_additional_branch",
            category="CONFIGURABLE",
            decision=recommend_second_branch,
            reason=(
                f"organizational_complexity score={org_score} (threshold={branch_threshold}), "
                f"branch_count={profile.get('branch_count')!r} -- NOT actionable today: the decision "
                "carries no branch name, POST /companies/{id}/branches has no duplicate-guard, and "
                "there is no safe way to revert a created branch (see gap analysis)."
            ),
            actionable=False,
        )
    )

    # CUSTOM_DEVELOPMENT -- multi-currency. docs/adaptive/03 §D is explicit:
    # this must be answered honestly against a real gap, never silently
    # dropped. The Core has no exchange_rate concept anywhere and no
    # currency-creation service (only seed-time inserts) -- this is not a
    # missing CRUD screen like cost centers, it is a genuinely new Core
    # capability (docs/adaptive/06 §6.5 tier 4), so it stays informational
    # regardless of what the customer answered.
    want_multi_currency = bool(profile.get("multi_currency_requested"))
    decisions.append(
        BlueprintDecision(
            key="multi_currency_support",
            category="CUSTOM_DEVELOPMENT",
            decision=want_multi_currency,
            reason=(
                f"multi_currency_requested={profile.get('multi_currency_requested')} -- "
                "NOT actionable today: no exchange_rate concept or currency-creation service "
                "exists anywhere in the Core (see gap analysis, honesty gap not a build gap)."
            ),
            actionable=False,
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
