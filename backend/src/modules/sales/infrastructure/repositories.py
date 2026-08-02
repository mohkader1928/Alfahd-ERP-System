"""Repository implementations for Sales (Phase 8 §7)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.sales.infrastructure.models import (
    Quotation,
    QuotationLine,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
    ZatcaSubmission,
)


class QuotationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, quotation: Quotation, lines: list[QuotationLine]) -> Quotation:
        self.session.add(quotation)
        await self.session.flush()
        for line in lines:
            line.quotation_id = quotation.id
            self.session.add(line)
        await self.session.flush()
        return quotation

    async def get_by_id(self, quotation_id: UUID) -> Quotation | None:
        result = await self.session.execute(select(Quotation).where(Quotation.id == quotation_id))
        return result.scalar_one_or_none()

    async def get_lines(self, quotation_id: UUID) -> list[QuotationLine]:
        result = await self.session.execute(
            select(QuotationLine).where(QuotationLine.quotation_id == quotation_id)
        )
        return list(result.scalars().all())

    async def next_number(self, company_id: UUID) -> str:
        result = await self.session.execute(select(func.count()).where(Quotation.company_id == company_id))
        count = result.scalar_one()
        return f"QT-{count + 1:06d}"

    async def list_by_company(self, company_id: UUID, *, limit: int = 200) -> list[Quotation]:
        result = await self.session.execute(
            select(Quotation).where(Quotation.company_id == company_id).order_by(Quotation.quote_date.desc()).limit(limit)
        )
        return list(result.scalars().all())


class SalesOrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, order: SalesOrder, lines: list[SalesOrderLine]) -> SalesOrder:
        self.session.add(order)
        await self.session.flush()
        for line in lines:
            line.sales_order_id = order.id
            self.session.add(line)
        await self.session.flush()
        return order

    async def get_by_id(self, order_id: UUID) -> SalesOrder | None:
        result = await self.session.execute(select(SalesOrder).where(SalesOrder.id == order_id))
        return result.scalar_one_or_none()

    async def get_lines(self, order_id: UUID) -> list[SalesOrderLine]:
        result = await self.session.execute(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order_id)
        )
        return list(result.scalars().all())

    async def next_number(self, company_id: UUID) -> str:
        result = await self.session.execute(select(func.count()).where(SalesOrder.company_id == company_id))
        count = result.scalar_one()
        return f"SO-{count + 1:06d}"


class SalesInvoiceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, invoice: SalesInvoice, lines: list[SalesInvoiceLine]) -> SalesInvoice:
        self.session.add(invoice)
        await self.session.flush()
        for line in lines:
            line.sales_invoice_id = invoice.id
            self.session.add(line)
        await self.session.flush()
        return invoice

    async def get_by_id(self, invoice_id: UUID) -> SalesInvoice | None:
        result = await self.session.execute(select(SalesInvoice).where(SalesInvoice.id == invoice_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, invoice_id: UUID) -> SalesInvoice | None:
        """Phase 17D: row-locked read, used only by PaymentService's
        allocation check — closes the same class of concurrent-write race
        Phase 16B fixed for invoice issuance (two simultaneous payments
        against the same invoice must not both pass the outstanding-balance
        check before either commits)."""
        result = await self.session.execute(
            select(SalesInvoice).where(SalesInvoice.id == invoice_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_lines(self, invoice_id: UUID) -> list[SalesInvoiceLine]:
        result = await self.session.execute(
            select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice_id)
        )
        return list(result.scalars().all())

    async def next_number(self, company_id: UUID) -> str:
        result = await self.session.execute(select(func.count()).where(SalesInvoice.company_id == company_id))
        count = result.scalar_one()
        return f"INV-{count + 1:06d}"

    async def latest_zatca_submission_for_company(self, company_id: UUID) -> ZatcaSubmission | None:
        """Tail of the hash chain (Phase 7 §4 note) — the whole point of the
        chain is a total order per device/company, so this walks the most
        recently created submission across all of the company's invoices."""
        result = await self.session.execute(
            select(ZatcaSubmission)
            .join(SalesInvoice, SalesInvoice.id == ZatcaSubmission.sales_invoice_id)
            .where(SalesInvoice.company_id == company_id)
            .order_by(ZatcaSubmission.icv.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def sum_total_in_range(self, company_id: UUID, date_from: date, date_to: date) -> Decimal:
        """FR-RPT-003 — period sales KPI. Only counts tax/simplified
        invoices, not credit/debit notes, to keep the figure a plain gross-
        sales total rather than a net-of-returns figure."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(SalesInvoice.total_amount), 0)).where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
                SalesInvoice.invoice_type.in_(["tax", "simplified"]),
                SalesInvoice.status.in_(["cleared", "reported", "pending_submission"]),
            )
        )
        # COALESCE(SUM(...), 0) returns a bare unscaled 0 when there are no
        # matching rows (vs. a properly NUMERIC(18,4)-scaled value when
        # there are) — quantize explicitly so the API response is
        # consistent regardless of whether any rows matched.
        return Decimal(result.scalar_one()).quantize(Decimal("0.0001"))

    async def list_by_company(
        self, company_id: UUID, *, partner_id: UUID | None = None, limit: int = 500
    ) -> list[SalesInvoice]:
        query = select(SalesInvoice).where(SalesInvoice.company_id == company_id)
        if partner_id is not None:
            query = query.where(SalesInvoice.partner_id == partner_id)
        result = await self.session.execute(query.order_by(SalesInvoice.invoice_date.desc()).limit(limit))
        return list(result.scalars().all())


class ZatcaSubmissionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, submission: ZatcaSubmission) -> ZatcaSubmission:
        self.session.add(submission)
        await self.session.flush()
        return submission

    async def get_by_invoice_id(self, invoice_id: UUID) -> ZatcaSubmission | None:
        result = await self.session.execute(
            select(ZatcaSubmission).where(ZatcaSubmission.sales_invoice_id == invoice_id)
        )
        return result.scalar_one_or_none()

    async def list_pending(self, limit: int = 50) -> list[ZatcaSubmission]:
        result = await self.session.execute(
            select(ZatcaSubmission).where(ZatcaSubmission.status == "pending_submission").limit(limit)
        )
        return list(result.scalars().all())
