"""Pure domain types for ZATCA (Phase 8 §2 — no ORM/HTTP/crypto-library imports here)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

SUBMISSION_MODES = ("clearance", "reporting")
SUBMISSION_STATUSES = ("pending_submission", "cleared", "reported", "rejected")


@dataclass(frozen=True)
class InvoiceLineData:
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate_percent: Decimal
    line_total: Decimal
    tax_amount: Decimal


@dataclass(frozen=True)
class InvoiceData:
    """Everything the ZATCA module needs to build/sign/submit an invoice —
    deliberately decoupled from Sales' ORM model (Adapter pattern boundary,
    Phase 8 §6)."""

    invoice_id: UUID
    invoice_number: str
    invoice_type: str  # 'tax' | 'simplified' | 'credit_note' | 'debit_note'
    issue_datetime_iso: str
    seller_name: str
    seller_vat_number: str
    buyer_name: str | None
    buyer_vat_number: str | None
    currency_code: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    lines: list[InvoiceLineData]
    original_invoice_number: str | None = None  # set for credit/debit notes


@dataclass(frozen=True)
class GatewayResponse:
    """What an `IZatcaGateway` implementation returns — it only knows
    accept/reject, not the ICV/hash-chain bookkeeping (that's the
    application layer's job, computed before the gateway is ever called)."""

    status: str  # 'cleared' | 'reported' | 'rejected'
    zatca_response: dict | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class SubmissionResult:
    """The full record persisted to `zatca_submission` (Phase 7 §4) —
    assembled by the application layer from the gateway's `GatewayResponse`
    plus the hash-chain/QR/XML it computed."""

    status: str  # 'cleared' | 'reported' | 'rejected' | 'pending_submission'
    uuid_value: UUID
    icv: int
    previous_hash: str
    invoice_hash: str
    qr_payload: str
    xml_document: str
    zatca_response: dict | None = None
    error_message: str | None = None
