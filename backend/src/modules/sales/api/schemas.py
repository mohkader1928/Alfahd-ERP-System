"""Pydantic schemas for Sales, per Phase 10 §6.3."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr


class QuotationLineIn(BaseModel):
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    tax_rate_id: UUID


class QuotationCreateRequest(BaseModel):
    partner_id: UUID
    quote_date: date
    lines: list[QuotationLineIn]


class QuotationOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    number: str
    status: str
    quote_date: date
    total_amount: Decimal

    model_config = {"from_attributes": True}


class SalesOrderOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    quotation_id: UUID | None
    number: str
    status: str
    order_date: date
    total_amount: Decimal

    model_config = {"from_attributes": True}


class ZatcaSubmissionOut(BaseModel):
    id: UUID
    uuid_value: UUID
    icv: int
    invoice_hash: str
    qr_payload: str
    submission_mode: str
    status: str

    model_config = {"from_attributes": True}


class SalesInvoiceOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    sales_order_id: UUID | None
    original_invoice_id: UUID | None
    invoice_type: str
    number: str
    status: str
    invoice_date: date
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    last_emailed_at: datetime | None = None
    last_emailed_to: str | None = None

    model_config = {"from_attributes": True}


class InvoiceIssueResponse(BaseModel):
    invoice: SalesInvoiceOut
    zatca_submission: ZatcaSubmissionOut


class CreditNoteCreateRequest(BaseModel):
    reason: str
    # Product Owner request: a credit note previously reversed only the
    # financial side (AR/Revenue/VAT), never the goods themselves — this
    # makes it a true "Sales Return" when true (the common case: goods are
    # physically coming back). False keeps the old financial-only behavior
    # for cases where the goods are NOT coming back (e.g. a price
    # correction, or goods damaged beyond resale).
    restock: bool = True


class SendInvoiceEmailRequest(BaseModel):
    to_email: EmailStr | None = None
