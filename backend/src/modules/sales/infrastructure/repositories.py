"""Repository implementations for Sales (Phase 8 §7)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, delete, func, select
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

    async def replace_lines(self, quotation_id: UUID, lines: list[QuotationLine]) -> None:
        """Full replace, not a diff — only ever called against a still-draft
        quotation (no downstream document references a line's own id yet),
        so there's nothing a line-level diff would preserve."""
        await self.session.execute(delete(QuotationLine).where(QuotationLine.quotation_id == quotation_id))
        for line in lines:
            line.quotation_id = quotation_id
            self.session.add(line)
        await self.session.flush()

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

    async def get_line_by_id_for_update(self, line_id: UUID) -> SalesOrderLine | None:
        """Row-locked read — mirrors PurchaseOrderRepository's own
        get_line_by_id_for_update. Without this, two concurrent partial
        invoice requests against the same order line can both read the
        same qty_invoiced and both pass the not-over-invoiced check,
        over-invoicing past what was actually ordered (same race the
        Purchasing side already closed for qty_received/qty_billed).

        `populate_existing=True` is required, not optional, whenever this
        line was already loaded earlier in the same request via a plain
        (unlocked) `get_lines()` call — which `issue_invoice_from_order`
        always does first. Without it, SQLAlchemy's identity map returns
        the *original* Python object once the lock is acquired, with its
        stale pre-lock `qty_invoiced` still intact, silently discarding
        the fresh row the FOR UPDATE query just read. The lock itself
        still blocks correctly; only the returned attribute values were
        wrong, which made two concurrent requests both see qty_invoiced=0
        and both invoice the same quantity — caught by
        test_concurrent_duplicate_invoice_exactly_one_succeeds (got
        [201, 201] instead of [201, 422] before this fix)."""
        result = await self.session.execute(
            select(SalesOrderLine)
            .where(SalesOrderLine.id == line_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def replace_lines(self, order_id: UUID, lines: list[SalesOrderLine]) -> None:
        await self.session.execute(delete(SalesOrderLine).where(SalesOrderLine.sales_order_id == order_id))
        for line in lines:
            line.sales_order_id = order_id
            self.session.add(line)
        await self.session.flush()

    async def next_number(self, company_id: UUID) -> str:
        result = await self.session.execute(select(func.count()).where(SalesOrder.company_id == company_id))
        count = result.scalar_one()
        return f"SO-{count + 1:06d}"

    async def list_by_company(self, company_id: UUID, *, limit: int = 200) -> list[SalesOrder]:
        result = await self.session.execute(
            select(SalesOrder).where(SalesOrder.company_id == company_id).order_by(SalesOrder.order_date.desc()).limit(limit)
        )
        return list(result.scalars().all())


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

    async def next_number(self, company_id: UUID, invoice_type: str = "tax") -> str:
        """Owner request: a Sales Return must read as its own document type,
        not just another invoice interleaved in the same series -- mirrors
        the precedent already set for Payments (RCT-/PAY-, scoped by
        payment_type). A credit note gets its own CN- prefix; tax and
        simplified invoices keep sharing one INV- prefix exactly as before.

        MUST be based on the highest existing NUMBER actually carrying this
        prefix, not a COUNT of same-type rows: every real company already
        has years of tax/simplified invoices and credit notes interleaved
        in one shared INV- sequence from before this change existed (e.g.
        INV-000079 already a 'tax' row alongside INV-000078/080 already
        'credit_note' rows). A same-type COUNT can land on a smaller number
        than the highest INV- number actually in use and collide with an
        already-issued one -- caught live: company_id
        fd009389-7c82-4cf3-95f8-515eca882894 hit exactly this on
        INV-000079. Scanning existing INV-prefixed numbers for their real
        max (regardless of which type originally claimed them) can never
        re-issue one that's taken, for old interleaved data or new
        type-separated data alike."""
        if invoice_type == "credit_note":
            prefix = "CN"
        elif invoice_type == "debit_note":
            prefix = "DN"
        else:
            prefix = "INV"
        result = await self.session.execute(
            select(SalesInvoice.number).where(
                SalesInvoice.company_id == company_id, SalesInvoice.number.like(f"{prefix}-%")
            )
        )
        max_seq = 0
        for (number,) in result.all():
            suffix = number.split("-", 1)[1] if "-" in number else ""
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
        return f"{prefix}-{max_seq + 1:06d}"

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
        """FR-RPT-003 — Dashboard's period/trend sales KPI. Owner request:
        this must be NET sales -- tax/simplified invoices minus credit
        notes issued in the same period. `debit_note` is a declared
        `invoice_type` with no creation path anywhere in Sales yet, so it
        is deliberately left out of both sides of the CASE below rather
        than guessed at; add it explicitly once that feature exists."""
        result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (SalesInvoice.invoice_type == "credit_note", -SalesInvoice.total_amount),
                            else_=SalesInvoice.total_amount,
                        )
                    ),
                    0,
                )
            ).where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
                SalesInvoice.invoice_type.in_(["tax", "simplified", "credit_note"]),
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

    async def list_by_company_page(
        self,
        company_id: UUID,
        *,
        partner_id: UUID | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        invoice_type: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[SalesInvoice], int]:
        """List-view server-side filtering (Product Owner audit): the
        plain `list_by_company` above hardcodes `limit=500` with no
        offset, so a company with more than 500 invoices silently loses
        access to older ones in the list screen — a real data-visibility
        bug, not just a performance nice-to-have. Real `LIMIT`/`OFFSET`
        plus a matching `COUNT(*)` so the caller always knows the true
        total, regardless of how many rows are actually returned.
        `invoice_type` (P0-9): lets the dedicated Sales Returns screen
        ask for exactly `credit_note` rows server-side, instead of
        fetching everything and filtering client-side."""
        conditions = [SalesInvoice.company_id == company_id]
        if partner_id is not None:
            conditions.append(SalesInvoice.partner_id == partner_id)
        if status is not None:
            conditions.append(SalesInvoice.status == status)
        if date_from is not None:
            conditions.append(SalesInvoice.invoice_date >= date_from)
        if date_to is not None:
            conditions.append(SalesInvoice.invoice_date <= date_to)
        if invoice_type is not None:
            conditions.append(SalesInvoice.invoice_type == invoice_type)

        count_result = await self.session.execute(select(func.count()).select_from(SalesInvoice).where(*conditions))
        total = count_result.scalar_one()

        rows_result = await self.session.execute(
            select(SalesInvoice)
            .where(*conditions)
            .order_by(SalesInvoice.invoice_date.desc(), SalesInvoice.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows_result.scalars().all()), total


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
