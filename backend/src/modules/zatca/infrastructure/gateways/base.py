"""IZatcaGateway — the Adapter interface (Phase 8 §6). Sales depends only on
this Protocol; which concrete gateway is wired in is a DI/config concern
keyed off `company.zatca_environment` (FR-ZATCA-012)."""

from typing import Protocol

from src.modules.zatca.domain.entities import GatewayResponse, InvoiceData


class IZatcaGateway(Protocol):
    async def clear_invoice(
        self, invoice: InvoiceData, *, xml_document: str, qr_payload: str, invoice_hash: str
    ) -> GatewayResponse:
        """Synchronous Clearance (FR-ZATCA-008) — used for Standard/Tax invoices."""
        ...

    async def report_invoice(
        self, invoice: InvoiceData, *, xml_document: str, qr_payload: str, invoice_hash: str
    ) -> GatewayResponse:
        """Asynchronous Reporting (FR-ZATCA-007) — used for Simplified invoices."""
        ...
