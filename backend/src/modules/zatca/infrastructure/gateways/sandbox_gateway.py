"""Simulated ZATCA gateway. Does NOT call the real ZATCA platform — there
are no CSID credentials to authenticate with (see module docstring). Mimics
accept/reject behavior deterministically so the rest of the system (retry
logic, status tracking, UI) has something real to integrate against and
test — swap for a real HTTP-calling implementation behind the same
`IZatcaGateway` interface once production credentials exist (FR-ZATCA-012).
"""

from src.modules.zatca.domain.entities import GatewayResponse, InvoiceData


class SandboxZatcaGateway:
    """NOT A REAL ZATCA INTEGRATION. See module docstring."""

    async def clear_invoice(
        self, invoice: InvoiceData, *, xml_document: str, qr_payload: str, invoice_hash: str
    ) -> GatewayResponse:
        if invoice.total_amount < 0:
            return GatewayResponse(
                status="rejected",
                error_message="Simulated validation error: total amount cannot be negative",
            )
        return GatewayResponse(
            status="cleared",
            zatca_response={
                "simulated": True,
                "clearanceStatus": "CLEARED",
                "invoiceHash": invoice_hash,
            },
        )

    async def report_invoice(
        self, invoice: InvoiceData, *, xml_document: str, qr_payload: str, invoice_hash: str
    ) -> GatewayResponse:
        if invoice.total_amount < 0:
            return GatewayResponse(
                status="rejected",
                error_message="Simulated validation error: total amount cannot be negative",
            )
        return GatewayResponse(
            status="reported",
            zatca_response={
                "simulated": True,
                "reportingStatus": "REPORTED",
                "invoiceHash": invoice_hash,
            },
        )
