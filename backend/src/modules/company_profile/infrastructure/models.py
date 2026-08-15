"""SQLAlchemy ORM model for Company Profile (Adaptive ERP Stage 2.1).

See docs/adaptive/06-configuration-engine-architecture.md §6.3: a separate
table, 1:1 with `company.id`, deliberately NOT new columns on `company`
itself — `Company` is touched by every RLS policy and every auth path in
the Core, so keeping profile data in its own table keeps this initiative
additive and risk-free to that table's shape (docs/adaptive/02
§2.2, docs/adaptive/03 "Data model implication").
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.infrastructure.db.base import Base, TenantScopedMixin


class CompanyProfile(Base, TenantScopedMixin):
    __tablename__ = "company_profile"

    # A. Company identity
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_form: Mapped[str | None] = mapped_column(Text, nullable=True)

    # B. Organization
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    branch_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_center_tracking_needed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # C. Operations
    is_service_business: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    warehouse_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_sales_order_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_purchase_order_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sku_count_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # D. Finance
    coa_depth_preference: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    multi_currency_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # E. Tax
    withholding_tax_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # F. Assets
    owns_fixed_assets: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fixed_asset_count_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # H. Management / Governance
    approval_rigor_preference: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'low'"))

    # I. Security
    desired_user_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    two_factor_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # G. Growth — capture-only, see domain/entities.py's docstring.
    growth_notes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        UniqueConstraint("company_id", name="ux_company_profile_company_id"),
        CheckConstraint(
            "approval_rigor_preference IN ('low','medium','high')",
            name="ck_company_profile_approval_rigor",
        ),
        CheckConstraint(
            "coa_depth_preference IS NULL OR (coa_depth_preference BETWEEN 1 AND 4)",
            name="ck_company_profile_coa_depth",
        ),
    )


class SizingRuleSet(Base):
    """Versioned Sizing Engine weights/thresholds (docs/adaptive/04 §4.3).

    Deliberately NOT tenant-scoped — this is a global rule catalog shared
    by every company, the same kind of table as the Core's own
    `Permission`/`Currency`/`AccountType` (seeded reference data, no
    company_id, no RLS needed)."""

    __tablename__ = "sizing_rule_set"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    version: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class SizingResult(Base, TenantScopedMixin):
    __tablename__ = "sizing_result"

    company_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_profile.id"), nullable=False, index=True
    )
    rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
