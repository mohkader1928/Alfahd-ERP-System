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
    payment_terms: str | None = None
    lines: list[QuotationLineIn]


class QuotationOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    number: str
    status: str
    quote_date: date
    total_amount: Decimal
    payment_terms: str | None = None
    last_emailed_at: datetime | None = None
    last_emailed_to: str | None = None

    model_config = {"from_attributes": True}


class SendQuotationEmailRequest(BaseModel):
    to_email: EmailStr | None = None


class QuotationLineOut(BaseModel):
    id: UUID
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    tax_rate_id: UUID

    model_config = {"from_attributes": True}


class QuotationDetailResponse(BaseModel):
    quotation: QuotationOut
    lines: list[QuotationLineOut]


class SalesOrderOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    quotation_id: UUID | None
    number: str
    status: str
    order_date: date
    total_amount: Decimal
    cancellation_reason: str | None

    model_config = {"from_attributes": True}


class SalesOrderLineOut(BaseModel):
    id: UUID
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    qty_invoiced: Decimal

    model_config = {"from_attributes": True}


class SalesOrderDetailResponse(BaseModel):
    order: SalesOrderOut
    lines: list[SalesOrderLineOut]


class SalesOrderLineIn(BaseModel):
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    tax_rate_id: UUID


class UpdateSalesOrderRequest(BaseModel):
    partner_id: UUID
    order_date: date
    lines: list[SalesOrderLineIn]


class CancelSalesOrderRequest(BaseModel):
    reason: str


class InvoiceLineQtyIn(BaseModel):
    sales_order_line_id: UUID
    qty: Decimal


class IssueInvoiceRequest(BaseModel):
    """Product Owner request (SO-000035): omitting `lines` invoices
    everything still remaining on the order (the original all-at-once
    behavior); passing `lines` invoices only that subset/quantity now,
    leaving the rest open as a backorder to invoice later — standard
    partial-fulfillment practice for a stock shortfall."""

    lines: list[InvoiceLineQtyIn] | None = None


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
    journal_entry_id: UUID | None
    last_emailed_at: datetime | None = None
    last_emailed_to: str | None = None

    model_config = {"from_attributes": True}


class SalesInvoiceLineOut(BaseModel):
    id: UUID
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    tax_rate_id: UUID

    model_config = {"from_attributes": True}


class InvoiceIssueResponse(BaseModel):
    invoice: SalesInvoiceOut
    zatca_submission: ZatcaSubmissionOut
    # Only populated by GET /invoices/{id} (the Sales Return screen needs the
    # original lines to prefill from) — every write-path route that returns
    # this shape (issue/credit-note/return) leaves it empty, since none of
    # them need to echo lines back.
    lines: list[SalesInvoiceLineOut] = []


class CreditNoteCreateRequest(BaseModel):
    reason: str
    # Product Owner request: a credit note previously reversed only the
    # financial side (AR/Revenue/VAT), never the goods themselves — this
    # makes it a true "Sales Return" when true (the common case: goods are
    # physically coming back). False keeps the old financial-only behavior
    # for cases where the goods are NOT coming back (e.g. a price
    # correction, or goods damaged beyond resale).
    restock: bool = True


class CreditNoteLineIn(BaseModel):
    product_id: UUID
    qty: Decimal
    unit_price: Decimal
    tax_rate_id: UUID


class CreditNoteLinesCreateRequest(BaseModel):
    """Product Owner request: a Sales Return is not necessarily for one
    whole invoice — it can be a freeform set of lines that were never on
    a single invoice together. `original_invoice_id` becomes purely
    optional/informational (kept only for traceability when the return
    genuinely does correspond to one invoice); the customer must be
    stated explicitly since there may be no original document to infer
    it from."""

    partner_id: UUID
    original_invoice_id: UUID | None = None
    reason: str
    restock: bool = True
    lines: list[CreditNoteLineIn]


class SendInvoiceEmailRequest(BaseModel):
    to_email: EmailStr | None = None

