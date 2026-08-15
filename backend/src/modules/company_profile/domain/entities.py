"""Domain entities for Adaptive ERP — Company Profile (Stage 2.1).

Pure dataclasses, no ORM/HTTP imports, per the Core's established
domain/application/infrastructure/api layering. Grounded in
docs/adaptive/03-customer-profile-spec.md — every field here maps to a row
in that spec's A-I tables and to a real Sizing Engine input
(docs/adaptive/04-erp-sizing-engine-spec.md §4.2). Section G (Growth) is
deliberately NOT scored by the Sizing Engine — see docs/adaptive/04 §4.2
and docs/adaptive/07 §7.3, which both treat "current state" and "growth
intent" as separate concerns; growth answers are captured for future
Growth Blueprint work (out of Stage 2 scope) via `growth_notes` only.
"""

import uuid
from dataclasses import dataclass, field

APPROVAL_RIGOR_LEVELS = ("low", "medium", "high")

# docs/adaptive/04-erp-sizing-engine-spec.md §4.2 — the 8 initial dimensions.
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


@dataclass
class CompanyProfile:
    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID

    # A. Company identity (docs/adaptive/03 §A)
    industry: str | None = None
    legal_form: str | None = None

    # B. Organization (§B)
    employee_count: int | None = None
    branch_count: int | None = None
    cost_center_tracking_needed: bool = False

    # C. Operations (§C)
    is_service_business: bool = False
    warehouse_count: int | None = None
    monthly_sales_order_volume: int | None = None
    monthly_purchase_order_volume: int | None = None
    sku_count_estimate: int | None = None

    # D. Finance (§D) — Company.valuation_method/fiscal_year_start_month
    # already exist on the Golden Core's own Company entity and are
    # intentionally NOT duplicated here (docs/adaptive/06 §6.3).
    coa_depth_preference: int | None = None
    multi_currency_requested: bool = False

    # E. Tax (§E) — VAT/ZATCA already live on Company; only the one
    # profile-specific signal not already captured anywhere is kept here.
    withholding_tax_needed: bool = False

    # F. Assets (§F)
    owns_fixed_assets: bool = False
    fixed_asset_count_estimate: int | None = None

    # H. Management / Governance (§H)
    approval_rigor_preference: str = "low"

    # I. Security (§I)
    desired_user_count: int | None = None
    two_factor_required: bool = False

    # G. Growth (§G) — capture-only, never read by the Sizing Engine.
    growth_notes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.approval_rigor_preference not in APPROVAL_RIGOR_LEVELS:
            raise ValueError(
                f"approval_rigor_preference must be one of {APPROVAL_RIGOR_LEVELS}"
            )
        if self.coa_depth_preference is not None and not (1 <= self.coa_depth_preference <= 4):
            raise ValueError("coa_depth_preference must be between 1 and 4")
        for field_name in (
            "employee_count",
            "branch_count",
            "warehouse_count",
            "monthly_sales_order_volume",
            "monthly_purchase_order_volume",
            "sku_count_estimate",
            "fixed_asset_count_estimate",
            "desired_user_count",
        ):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} cannot be negative")


@dataclass(frozen=True)
class DimensionScore:
    """One Sizing Engine dimension's result — docs/adaptive/04 §4.4
    (Explainability): a score alone is never valid without its reason."""

    score: int
    reason: str

    def __post_init__(self) -> None:
        if not (0 <= self.score <= 100):
            raise ValueError("score must be between 0 and 100")
        if not self.reason:
            raise ValueError("reason is required — a score without an explanation is not valid output")


@dataclass
class SizingResult:
    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    company_profile_id: uuid.UUID
    rule_version: str
    dimensions: dict[str, DimensionScore] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = set(SIZING_DIMENSIONS) - set(self.dimensions)
        if missing:
            raise ValueError(f"missing dimension scores: {sorted(missing)}")
