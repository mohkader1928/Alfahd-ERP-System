"""ZatcaInvoiceProcessor — the module's single orchestration entry point.

Deliberately stateless / DB-free: Sales owns the `zatca_submission` table
(Phase 7 §4) and passes in the previous hash + ICV it already looked up,
receiving back a `SubmissionResult` to persist. This keeps ZATCA a pure,
easily-unit-tested library, per Phase 9's "internal only, no public routes"
note and the Adapter boundary from Phase 8 §6.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.zatca.domain.entities import InvoiceData, SubmissionResult
from src.modules.zatca.infrastructure.gateways.base import IZatcaGateway
from src.modules.zatca.infrastructure.hash_chain import compute_invoice_hash
from src.modules.zatca.infrastructure.qr_encoder import build_qr_payload
from src.modules.zatca.infrastructure.signing import ISigningService
from src.modules.zatca.infrastructure.xml_builder import build_invoice_xml


@dataclass(frozen=True)
class PreparedInvoice:
    """Locally-computed package — no gateway call yet. Used directly for
    Simplified invoices (FR-ZATCA-007: delivered to the customer immediately,
    Reporting happens later) and internally by `submit()` for the
    synchronous Clearance path."""

    uuid_value: uuid.UUID
    icv: int
    previous_hash: str
    invoice_hash: str
    qr_payload: str
    xml_document: str


class ZatcaInvoiceProcessor:
    def __init__(self, gateway: IZatcaGateway, signing_service: ISigningService):
        self.gateway = gateway
        self.signing_service = signing_service

    def prepare(self, invoice: InvoiceData, *, previous_hash: str, icv: int) -> PreparedInvoice:
        """Pure local computation: XML, hash chain, stamp placeholder, QR.
        No network/gateway I/O — safe to call inline in any request."""
        zatca_uuid = uuid.uuid4()

        xml_document = build_invoice_xml(invoice, uuid_value=str(zatca_uuid), icv=icv)
        invoice_hash = compute_invoice_hash(xml_document, previous_hash)
        stamp = self.signing_service.stamp(xml_document)  # NOT a real Cryptographic Stamp — see module docstring
        qr_payload = build_qr_payload(
            seller_name=invoice.seller_name,
            vat_number=invoice.seller_vat_number,
            timestamp_iso=invoice.issue_datetime_iso,
            invoice_total=invoice.total_amount,
            vat_amount=invoice.tax_amount,
            invoice_hash_b64=invoice_hash,
        )
        signed_xml_document = (
            f"{xml_document}<!-- CryptographicStampPlaceholder(NOT_ZATCA_COMPLIANT)=\"{stamp}\" -->"
        )

        return PreparedInvoice(
            uuid_value=zatca_uuid,
            icv=icv,
            previous_hash=previous_hash,
            invoice_hash=invoice_hash,
            qr_payload=qr_payload,
            xml_document=signed_xml_document,
        )

    async def submit_prepared(
        self, invoice: InvoiceData, prepared: PreparedInvoice, *, submission_mode: str
    ) -> SubmissionResult:
        """Calls the (simulated) gateway for an already-`prepare()`d package.
        Used for the synchronous Clearance path and for the Celery task that
        later reports a previously-prepared Simplified invoice."""
        if submission_mode == "clearance":
            gateway_response = await self.gateway.clear_invoice(
                invoice,
                xml_document=prepared.xml_document,
                qr_payload=prepared.qr_payload,
                invoice_hash=prepared.invoice_hash,
            )
        elif submission_mode == "reporting":
            gateway_response = await self.gateway.report_invoice(
                invoice,
                xml_document=prepared.xml_document,
                qr_payload=prepared.qr_payload,
                invoice_hash=prepared.invoice_hash,
            )
        else:
            raise ValueError(f"Unknown submission mode: {submission_mode}")

        return SubmissionResult(
            status=gateway_response.status,
            uuid_value=prepared.uuid_value,
            icv=prepared.icv,
            previous_hash=prepared.previous_hash,
            invoice_hash=prepared.invoice_hash,
            qr_payload=prepared.qr_payload,
            xml_document=prepared.xml_document,
            zatca_response=gateway_response.zatca_response,
            error_message=gateway_response.error_message,
        )

    async def submit(
        self,
        invoice: InvoiceData,
        *,
        previous_hash: str,
        icv: int,
        submission_mode: str,  # 'clearance' | 'reporting'
    ) -> SubmissionResult:
        """Convenience: prepare + submit in one call, for the synchronous path."""
        prepared = self.prepare(invoice, previous_hash=previous_hash, icv=icv)
        return await self.submit_prepared(invoice, prepared, submission_mode=submission_mode)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
