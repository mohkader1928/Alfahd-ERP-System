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


class SubledgerLine(BaseModel):
    date: date
    movement_type: str
    document_type: str
    document_id: UUID
    reference: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


class SubledgerResponse(BaseModel):
    partner_id: UUID
    partner_name: str
    date_from: date
    date_to: date
    opening_balance: Decimal
    lines: list[SubledgerLine]
    closing_balance: Decimal


class AgingRow(BaseModel):
    partner_id: UUID | None
    partner_name: str
    document_id: UUID
    number: str
    due_date: date
    balance_due: Decimal
    days_overdue: int
    bucket: str


class AgingResponse(BaseModel):
    as_of_date: date
    rows: list[AgingRow]
