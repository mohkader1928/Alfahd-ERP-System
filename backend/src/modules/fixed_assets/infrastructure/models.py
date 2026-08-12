"""SQLAlchemy ORM models for Fixed Assets (P0-5, 3-Day Brief), mirroring
the schema created in migration a4b5c6d7e8f9.

Accumulated depreciation and disposed/active status are deliberately not
columns here -- both are derived on read (sum of posted
FixedAssetDepreciationEntry rows; disposed_at IS NOT NULL) so they can
never drift from what was actually posted to the GL, the same
data-driven-status principle P0-1 established for purchase order status.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.infrastructure.db.base import Base


class FixedAssetCategory(Base):
    """Mirrors ProductCategory's minimal self-referencing tree exactly —
    same shape, same reasoning (identity/infrastructure/master_data_models.py)."""

    __tablename__ = "fixed_asset_category"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_asset_category.id"), nullable=True
    )


class FixedAsset(Base):
    __tablename__ = "fixed_asset"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_asset_category.id"), nullable=True
    )
    fixed_asset_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False
    )
    accumulated_depreciation_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False
    )
    depreciation_expense_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False
    )
    acquisition_date: Mapped[date] = mapped_column(nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    salvage_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    useful_life_months: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    acquisition_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True
    )
    disposed_at: Mapped[date | None] = mapped_column(nullable=True)
    disposal_proceeds: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    disposal_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint("cost > 0", name="ck_fixed_asset_cost_positive"),
        CheckConstraint("salvage_value >= 0", name="ck_fixed_asset_salvage_non_negative"),
        CheckConstraint("salvage_value < cost", name="ck_fixed_asset_salvage_below_cost"),
        CheckConstraint("useful_life_months > 0", name="ck_fixed_asset_useful_life_positive"),
        UniqueConstraint("company_id", "asset_code", name="ux_fixed_asset_code"),
    )


class FixedAssetDepreciationEntry(Base):
    __tablename__ = "fixed_asset_depreciation_entry"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    fixed_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixed_asset.id"), nullable=False, index=True
    )
    period_month: Mapped[date] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entry.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_fixed_asset_depreciation_amount_positive"),
        UniqueConstraint("fixed_asset_id", "period_month", name="ux_fixed_asset_depreciation_period"),
    )
