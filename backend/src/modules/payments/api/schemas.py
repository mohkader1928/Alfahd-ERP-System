"""Pydantic schemas for Payments (Phase 17D)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PaymentAllocationIn(BaseModel):
    sales_invoice_id: UUID | None = None
    vendor_bill_id: UUID | None = None
    amount: Decimal


class PaymentCreateRequest(BaseModel):
    partner_id: UUID
    payment_type: str
    payment_date: date
    amount: Decimal
    account_id: UUID
    reference: str | None = None
    allocations: list[PaymentAllocationIn] = []


class PaymentAllocationOut(BaseModel):
    id: UUID
    sales_invoice_id: UUID | None
    vendor_bill_id: UUID | None
    amount: Decimal

    model_config = {"from_attributes": True}


class PaymentOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    payment_type: str
    number: str
    payment_date: date
    amount: Decimal
    currency_code: str
    account_id: UUID
    reference: str | None
    journal_entry_id: UUID | None

    model_config = {"from_attributes": True}


class PaymentDetailResponse(BaseModel):
    payment: PaymentOut
    allocations: list[PaymentAllocationOut]


class DocumentBalanceOut(BaseModel):
    total_amount: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    payment_status: str
