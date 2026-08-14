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
# Sales Order gets its own status set (not the shared DOC_STATUSES, which
# Quotation also uses and doesn't need this state) — mirrors Purchasing's
# own PO_STATUSES, added for the identical reason: partial fulfillment.
# Product Owner-reported blocker: an order for more than what's currently
# in stock had no path forward (invoicing the whole order at once fails
# outright, and the order itself had no edit path either). Standard ERP
# practice is partial invoicing — invoice what's available now, leave the
# rest open as a backorder to invoice later.
SO_STATUSES = ("draft", "confirmed", "partially_invoiced", "done", "cancelled")


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
    # Owner request: which warehouse this quotation is expected to ship
    # from — carried forward unchanged by confirm_to_sales_order onto the
    # SalesOrder, and from there onto the SalesInvoice at issuance, so it
    # only needs choosing once. Nullable for pre-existing rows (see
    # migration f0a1b2c3d4e5); the create/update schemas require it.
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Owner request (Document Delivery for Quotations): defaults from
    # Partner.payment_terms at creation time but is a free edit from there
    # — the customer's own record is just the starting value, not enforced.
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_emailed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_emailed_to: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # Copied from the originating Quotation at confirm_to_sales_order time;
    # still editable via update_order as long as nothing's been invoiced.
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {SO_STATUSES}", name="ck_sales_order_status"),
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
    # Copied from the SalesOrder at issue_invoice_from_order time — the
    # warehouse _deduct_stock_for_lines actually issues stock from, and
    # what a Sales Return's restock resolves back to instead of always the
    # company default.
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    last_emailed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_emailed_to: Mapped[str | None] = mapped_column(Text, nullable=True)

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
