"""Pydantic schemas for Purchasing, per Phase 10 §6.5."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PurchaseOrderLineIn(BaseModel):
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    tax_rate_id: UUID


class PurchaseOrderCreateRequest(BaseModel):
    partner_id: UUID
    order_date: date
    warehouse_id: UUID | None = None
    lines: list[PurchaseOrderLineIn]


class PurchaseOrderLineOut(BaseModel):
    id: UUID
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    qty_received: Decimal
    qty_billed: Decimal
    short_closed: bool

    model_config = {"from_attributes": True}


class ShortClosePurchaseOrderRequest(BaseModel):
    reason: str


class PurchaseOrderOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    number: str
    status: str
    order_date: date
    total_amount: Decimal
    warehouse_id: UUID | None = None
    created_by_user_id: UUID | None
    approval_status: str
    approved_by: UUID | None
    approved_at: datetime | None
    rejection_reason: str | None

    model_config = {"from_attributes": True}


class PurchaseOrderDetailResponse(BaseModel):
    order: PurchaseOrderOut
    lines: list[PurchaseOrderLineOut]


class RejectPurchaseOrderRequest(BaseModel):
    reason: str


class GoodsReceiptLineIn(BaseModel):
    purchase_order_line_id: UUID
    qty: Decimal


class GoodsReceiptCreateRequest(BaseModel):
    lines: list[GoodsReceiptLineIn]


class GoodsReceiptOut(BaseModel):
    id: UUID
    purchase_order_id: UUID
    warehouse_id: UUID
    number: str
    status: str
    receipt_date: date

    model_config = {"from_attributes": True}


class VendorBillLineIn(BaseModel):
    purchase_order_line_id: UUID
    qty: Decimal
    unit_price: Decimal


class VendorBillCreateRequest(BaseModel):
    vendor_reference: str | None = None
    lines: list[VendorBillLineIn]


class DebitNoteCreateRequest(BaseModel):
    reason: str
    # Product Owner request: a debit note previously reversed only the
    # financial side (AP/GRNI/VAT), never the goods themselves — this
    # makes it a true "Purchase Return" when true (the common case: goods
    # are physically going back to the vendor). False keeps the old
    # financial-only behavior (e.g. a price correction with no physical
    # return).
    restock: bool = True


class DebitNoteLineIn(BaseModel):
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    tax_rate_id: UUID


class DebitNoteLinesCreateRequest(BaseModel):
    """Product Owner request: a Purchase Return is not necessarily for one
    whole vendor bill — it can be a freeform set of lines that were never
    on a single bill together. `original_bill_id` becomes purely
    optional/informational (kept only for traceability when the return
    genuinely does correspond to one bill); the vendor must be stated
    explicitly since there may be no original document to infer it from."""

    partner_id: UUID
    original_bill_id: UUID | None = None
    reason: str
    restock: bool = True
    lines: list[DebitNoteLineIn]


class VendorBillOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    purchase_order_id: UUID | None
    warehouse_id: UUID | None
    number: str
    vendor_reference: str | None
    status: str
    bill_date: date
    due_date: date | None
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    mismatch_reasons: str | None
    bill_type: str
    original_bill_id: UUID | None
    journal_entry_id: UUID | None

    model_config = {"from_attributes": True}


class VendorBillLineOut(BaseModel):
    id: UUID
    product_id: UUID
    purchase_order_line_id: UUID | None
    qty: Decimal
    unit_price: Decimal
    tax_rate_id: UUID
    tax_rate_percent: Decimal
    line_total: Decimal
    tax_amount: Decimal

    model_config = {"from_attributes": True}


class VendorBillDetailResponse(BaseModel):
    bill: VendorBillOut
    lines: list[VendorBillLineOut]
