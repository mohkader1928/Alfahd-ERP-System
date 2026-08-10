"""SQLAlchemy ORM models for Purchasing, mirroring Phase 7 §6 DDL
(RFQ granularity skipped — PO is created directly, matching how Sales
skips separate opportunity tracking; Debit Note deferred, Should-priority)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.infrastructure.db.base import Base

DOC_STATUSES = ("draft", "confirmed", "done", "cancelled")
BILL_STATUSES = ("draft", "matched", "mismatched", "approved", "posted")
# Purchase Order gets its own status set (not the shared DOC_STATUSES, which
# goods_receipt also uses and doesn't need this state): "pending_approval"
# is the Approval Workflow gate — a PO whose total exceeds the company's
# po_approval_threshold routes here instead of auto-confirming.
PO_STATUSES = ("draft", "pending_approval", "confirmed", "partially_received", "done", "closed", "cancelled")
PO_APPROVAL_STATUSES = ("not_required", "pending", "approved", "rejected")


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(Text, nullable=False, server_default="SAR")
    order_date: Mapped[date] = mapped_column(nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True
    )
    approval_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="not_required")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {PO_STATUSES}", name="ck_purchase_order_status"),
        CheckConstraint(f"approval_status IN {PO_APPROVAL_STATUSES}", name="ck_purchase_order_approval_status"),
        UniqueConstraint("company_id", "number", name="ux_purchase_order_number"),
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order.id"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty_received: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default=text("0"))
    qty_billed: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default=text("0"))
    # 3-Day Brief P0-1: deliberately stops short of the ordered qty
    # instead of leaving a partially-received PO open forever. Once set,
    # the remaining (qty - qty_received) can no longer be received until
    # an explicit admin reopen action clears this flag.
    short_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class GoodsReceipt(Base):
    __tablename__ = "goods_receipt"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order.id"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    receipt_date: Mapped[date] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {DOC_STATUSES}", name="ck_goods_receipt_status"),
        # The one document type in this module that shipped without its
        # sibling PurchaseOrder/VendorBill's UNIQUE(company_id, number) —
        # confirmed via direct pg_constraint query (docs/16b, finding #5) to
        # be the sole numbered document with zero backstop against a
        # duplicate number.
        UniqueConstraint("company_id", "number", name="ux_goods_receipt_number"),
    )


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_receipt.id"), nullable=False
    )
    purchase_order_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order_line.id"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    stock_move_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class VendorBill(Base):
    __tablename__ = "vendor_bill"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Nullable (Product Owner request): a freeform Purchase Return
    # (bill_type='debit_note' with no original_bill_id) has no PO of its
    # own to reference — a standard bill always sets this in practice, the
    # application layer enforces that, not this column.
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order.id"), nullable=True
    )
    number: Mapped[str] = mapped_column(Text, nullable=False)
    vendor_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(Text, nullable=False, server_default="SAR")
    bill_date: Mapped[date] = mapped_column(nullable=False)
    due_date: Mapped[date | None] = mapped_column(nullable=True)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    mismatch_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Vendor Debit Note (mirrors sales_invoice.invoice_type/original_invoice_id):
    # a debit note reverses a posted bill (goods return, price correction)
    # and inherits that bill's purchase_order_id rather than needing its
    # own PO — same "no PO of its own" shape a sales credit note has.
    bill_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="standard")
    original_bill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_bill.id"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"status IN {BILL_STATUSES}", name="ck_vendor_bill_status"),
        CheckConstraint("bill_type IN ('standard', 'debit_note')", name="ck_vendor_bill_type"),
        UniqueConstraint("company_id", "number", name="ux_vendor_bill_number"),
    )


class VendorBillLine(Base):
    __tablename__ = "vendor_bill_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    vendor_bill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vendor_bill.id"), nullable=False)
    # Nullable (Product Owner request): a freeform Purchase Return line has
    # no 3-way-matched PO line behind it — a standard bill's lines always
    # set this, enforced by the application layer, not this column.
    purchase_order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order_line.id"), nullable=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tax_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
