"""SQLAlchemy ORM models for Sales, mirroring Phase 7 §4 DDL (PriceList
tables deferred — FR-SAL-006 is Should-priority and Product.sales_price
already covers the M2 nucleus need; Delivery deferred to M3 per the M2
kickoff scope note)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.infrastructure.db.base import Base

DOC_STATUSES = ("draft", "confirmed", "done", "cancelled")


class Quotation(Base):
    __tablename__ = "quotation"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(Text, nullable=False, server_default="SAR")
    quote_date: Mapped[date] = mapped_column(nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {DOC_STATUSES}", name="ck_quotation_status"),
        UniqueConstraint("company_id", "number", name="ux_quotation_number"),
    )


class QuotationLine(Base):
    __tablename__ = "quotation_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Phase 16A: direct company_id (backfilled from quotation.company_id),
    # protected by its own RLS policy — not just isolated via the FK join.
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    quotation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quotation.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class SalesOrder(Base):
    __tablename__ = "sales_order"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quotation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("quotation.id"), nullable=True)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(Text, nullable=False, server_default="SAR")
    order_date: Mapped[date] = mapped_column(nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    version: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {DOC_STATUSES}", name="ck_sales_order_status"),
        UniqueConstraint("company_id", "number", name="ux_sales_order_number"),
    )


class SalesOrderLine(Base):
    __tablename__ = "sales_order_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sales_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sales_order.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty_invoiced: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default=text("0"))


INVOICE_TYPES = ("tax", "simplified", "credit_note", "debit_note")
INVOICE_STATUSES = ("draft", "pending_submission", "cleared", "reported", "rejected", "cancelled")


class SalesInvoice(Base):
    __tablename__ = "sales_invoice"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sales_order.id"), nullable=True)
    original_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_invoice.id"), nullable=True
    )
    invoice_type: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(Text, nullable=False, server_default="SAR")
    invoice_date: Mapped[date] = mapped_column(nullable=False)
    due_date: Mapped[date | None] = mapped_column(nullable=True)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint(f"invoice_type IN {INVOICE_TYPES}", name="ck_sales_invoice_type"),
        CheckConstraint(f"status IN {INVOICE_STATUSES}", name="ck_sales_invoice_status"),
        UniqueConstraint("company_id", "number", name="ux_sales_invoice_number"),
    )


class SalesInvoiceLine(Base):
    __tablename__ = "sales_invoice_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sales_invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_invoice.id"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tax_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


class ZatcaSubmission(Base):
    __tablename__ = "zatca_submission"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sales_invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_invoice.id"), nullable=False
    )
    uuid_value: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    icv: Mapped[int] = mapped_column(nullable=False)
    previous_hash: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_hash: Mapped[str] = mapped_column(Text, nullable=False)
    qr_payload: Mapped[str] = mapped_column(Text, nullable=False)
    xml_document: Mapped[str] = mapped_column(Text, nullable=False)
    submission_mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending_submission")
    zatca_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    retry_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint("submission_mode IN ('clearance','reporting')", name="ck_zatca_submission_mode"),
        CheckConstraint(f"status IN {INVOICE_STATUSES}", name="ck_zatca_submission_status"),
        Index("ux_zatca_invoice", "sales_invoice_id", unique=True),
    )
