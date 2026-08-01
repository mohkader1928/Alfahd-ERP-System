"""SQLAlchemy ORM models for Purchasing, mirroring Phase 7 §6 DDL
(RFQ granularity skipped — PO is created directly, matching how Sales
skips separate opportunity tracking; Debit Note deferred, Should-priority)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.infrastructure.db.base import Base

DOC_STATUSES = ("draft", "confirmed", "done", "cancelled")
BILL_STATUSES = ("draft", "matched", "mismatched", "approved", "posted")


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

    __table_args__ = (
        CheckConstraint(f"status IN {DOC_STATUSES}", name="ck_purchase_order_status"),
        UniqueConstraint("company_id", "number", name="ux_purchase_order_number"),
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order.id"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty_received: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default=text("0"))
    qty_billed: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, server_default=text("0"))


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

    __table_args__ = (CheckConstraint(f"status IN {DOC_STATUSES}", name="ck_goods_receipt_status"),)


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
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
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order.id"), nullable=False
    )
    number: Mapped[str] = mapped_column(Text, nullable=False)
    vendor_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(Text, nullable=False, server_default="SAR")
    bill_date: Mapped[date] = mapped_column(nullable=False)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    mismatch_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {BILL_STATUSES}", name="ck_vendor_bill_status"),
        UniqueConstraint("company_id", "number", name="ux_vendor_bill_number"),
    )


class VendorBillLine(Base):
    __tablename__ = "vendor_bill_line"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    vendor_bill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vendor_bill.id"), nullable=False)
    purchase_order_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_order_line.id"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tax_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
