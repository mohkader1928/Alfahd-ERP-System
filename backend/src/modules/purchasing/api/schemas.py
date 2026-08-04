"""Pydantic schemas for Purchasing, per Phase 10 §6.5."""

from datetime import date
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
    lines: list[PurchaseOrderLineIn]


class PurchaseOrderLineOut(BaseModel):
    id: UUID
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    qty_received: Decimal
    qty_billed: Decimal

    model_config = {"from_attributes": True}


class PurchaseOrderOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    number: str
    status: str
    order_date: date
    total_amount: Decimal

    model_config = {"from_attributes": True}


class PurchaseOrderDetailResponse(BaseModel):
    order: PurchaseOrderOut
    lines: list[PurchaseOrderLineOut]


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


class VendorBillOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    purchase_order_id: UUID
    number: str
    vendor_reference: str | None
    status: str
    bill_date: date
    due_date: date | None
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    mismatch_reasons: str | None

    model_config = {"from_attributes": True}


class VendorBillLineOut(BaseModel):
    id: UUID
    product_id: UUID
    purchase_order_line_id: UUID
    qty: Decimal
    unit_price: Decimal
    tax_rate_percent: Decimal
    line_total: Decimal
    tax_amount: Decimal

    model_config = {"from_attributes": True}


class VendorBillDetailResponse(BaseModel):
    bill: VendorBillOut
    lines: list[VendorBillLineOut]
