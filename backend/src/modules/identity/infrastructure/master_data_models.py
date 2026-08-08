"""Partner (customer/vendor) and Product master data, per FR-CORE-042/045.

Kept in a separate module file from identity's core auth/RBAC models for
readability, but still owned by the Identity module/migration namespace —
this is shared master data every downstream module (Sales, Purchasing,
Inventory) references, per the Phase 6 ER diagram §2.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.infrastructure.db.base import Base


class Partner(Base):
    """Unified Address Book / Partner & Contacts bundle: Partner is the one
    master entity for company/individual, customer/vendor/employee, and
    contact person — there is no separate `partner_contact` table. A
    "contact person" is a Partner row with `is_company=false` and
    `parent_partner_id` set to the company it belongs to; it can later gain
    `is_customer`/`is_vendor`/`is_employee` on that same row (no re-creation
    of identity data) — see the migration docstring for the full rationale.
    """

    __tablename__ = "partner"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_company: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    parent_partner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partner.id", ondelete="SET NULL"), nullable=True
    )
    is_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_vendor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_employee: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    job_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    mobile: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    vat_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    cr_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """Deprecated JSONB single-address field, kept post-backfill (not
    dropped) per explicit Owner instruction — superseded by PartnerAddress.
    No code writes to this column anymore; see migration b2c4e6f8a1d3."""
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_partner_company", "company_id"),
        Index("ix_partner_parent", "parent_partner_id"),
        Index(
            "ux_partner_vat",
            "company_id",
            "vat_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND vat_number IS NOT NULL"),
        ),
    )

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None


class PartnerAddress(Base):
    """One of possibly several structured addresses for a Partner —
    Billing/Shipping/Other, with at most one default per (partner, type).
    A stable, FK-able primary key from day one so Sales/Purchasing can
    later reference a specific address (e.g. a Sales Invoice's billing
    address) without restructuring this table."""

    __tablename__ = "partner_address"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partner.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    street: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()"), nullable=False
    )


class ProductCategory(Base):
    __tablename__ = "product_category"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_category.id"), nullable=True
    )


class UnitOfMeasure(Base):
    __tablename__ = "unit_of_measure"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("ux_uom_company_code", "company_id", "code", unique=True),
    )


class Product(Base):
    __tablename__ = "product"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_category.id"), nullable=True
    )
    uom_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unit_of_measure.id"), nullable=True, index=True
    )
    is_stockable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sales_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    default_tax_rate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reorder_point: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ux_product_sku", "company_id", "sku", unique=True, postgresql_where=text("deleted_at IS NULL")),
    )
