"""Reporting services — Phase 8 §3: Reporting is the only module allowed to
read across other modules' repositories directly (read-only query
interfaces, not shared tables), since dashboards inherently aggregate
cross-module data (FR-RPT-003)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.infrastructure.repositories import JournalEntryRepository
from src.modules.identity.infrastructure.master_data_models import Partner, Product
from src.modules.purchasing.infrastructure.repositories import VendorBillRepository
from src.modules.sales.infrastructure.models import SalesInvoice, SalesInvoiceLine
from src.modules.sales.infrastructure.repositories import SalesInvoiceRepository

ACCOUNT_CODE_AR = "1200"
ACCOUNT_CODE_AP = "2100"


@dataclass(frozen=True)
class DashboardSummary:
    period_start: date
    period_end: date
    period_sales_total: Decimal
    period_purchases_total: Decimal
    receivables_balance: Decimal
    payables_balance: Decimal


class DashboardService:
    def __init__(
        self,
        invoice_repo: SalesInvoiceRepository,
        bill_repo: VendorBillRepository,
        journal_entry_repo: JournalEntryRepository,
    ):
        self.invoice_repo = invoice_repo
        self.bill_repo = bill_repo
        self.journal_entry_repo = journal_entry_repo

    async def get_summary(self, *, company_id: UUID, period_start: date, period_end: date) -> DashboardSummary:
        sales_total = await self.invoice_repo.sum_total_in_range(company_id, period_start, period_end)
        purchases_total = await self.bill_repo.sum_total_in_range(company_id, period_start, period_end)
        # AR is a normal-debit account (asset): positive balance = amount owed to us.
        ar_balance = await self.journal_entry_repo.account_balance(company_id, ACCOUNT_CODE_AR, period_end)
        # AP is a normal-credit account (liability): flip sign for a positive "amount we owe" figure.
        ap_balance = -(await self.journal_entry_repo.account_balance(company_id, ACCOUNT_CODE_AP, period_end))

        return DashboardSummary(
            period_start=period_start,
            period_end=period_end,
            period_sales_total=sales_total,
            period_purchases_total=purchases_total,
            receivables_balance=ar_balance,
            payables_balance=ap_balance,
        )


# ── Sales Reporting ────────────────────────────────────────────────────────────
# Reporting module is the only one permitted to query across module boundaries
# (FR-RPT-003).  These queries touch Sales + Identity (Partner, Product) tables
# directly via SQLAlchemy, consistent with how DashboardService already uses
# SalesInvoiceRepository and JournalEntryRepository from other modules.

# Statuses that represent a real, finalized sale (ZATCA submitted/cleared or
# pending submission). Draft / rejected / cancelled are excluded so the report
# reflects actual revenue, not work-in-progress.
_FINALIZED_STATUSES = ("pending_submission", "cleared", "reported")

# Invoice types that represent forward sales (not reversals / debit notes).
# credit_note and debit_note are intentionally excluded from the aggregates;
# they would need separate "returns" columns to be meaningful and are not
# included in the current scope of the report.
_FORWARD_INVOICE_TYPES = ("tax", "simplified")


class SalesReportingService:
    """FR-RPT — cross-module Sales reporting queries.

    All queries are read-only and join Sales tables with the Identity
    (Partner/Product) master-data tables — permitted only from this module.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_customer(
        self, *, company_id: UUID, date_from: date, date_to: date
    ) -> list[dict]:
        """Aggregate invoiced sales grouped by customer (partner)."""
        stmt = (
            select(
                Partner.id.label("partner_id"),
                Partner.name.label("partner_name"),
                func.count(SalesInvoice.id).label("invoice_count"),
                func.coalesce(func.sum(SalesInvoice.subtotal_amount), 0).label("subtotal"),
                func.coalesce(func.sum(SalesInvoice.tax_amount), 0).label("tax_amount"),
                func.coalesce(func.sum(SalesInvoice.total_amount), 0).label("total"),
            )
            .join(Partner, Partner.id == SalesInvoice.partner_id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status.in_(_FINALIZED_STATUSES),
                SalesInvoice.invoice_type.in_(_FORWARD_INVOICE_TYPES),
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
            )
            .group_by(Partner.id, Partner.name)
            .order_by(func.sum(SalesInvoice.total_amount).desc())
        )
        result = await self.session.execute(stmt)
        return [
            {
                "partner_id": row.partner_id,
                "partner_name": row.partner_name,
                "invoice_count": row.invoice_count,
                "subtotal": Decimal(str(row.subtotal)),
                "tax_amount": Decimal(str(row.tax_amount)),
                "total": Decimal(str(row.total)),
            }
            for row in result.all()
        ]

    async def by_product(
        self, *, company_id: UUID, date_from: date, date_to: date
    ) -> list[dict]:
        """Aggregate invoiced sales grouped by product (via invoice lines)."""
        stmt = (
            select(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.sku.label("product_code"),
                func.coalesce(func.sum(SalesInvoiceLine.qty), 0).label("qty_sold"),
                func.coalesce(func.sum(SalesInvoiceLine.line_total), 0).label("subtotal"),
                func.coalesce(func.sum(SalesInvoiceLine.tax_amount), 0).label("tax_amount"),
                func.coalesce(
                    func.sum(SalesInvoiceLine.line_total + SalesInvoiceLine.tax_amount), 0
                ).label("total"),
            )
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .join(Product, Product.id == SalesInvoiceLine.product_id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status.in_(_FINALIZED_STATUSES),
                SalesInvoice.invoice_type.in_(_FORWARD_INVOICE_TYPES),
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
            )
            .group_by(Product.id, Product.name, Product.sku)
            .order_by(func.sum(SalesInvoiceLine.line_total + SalesInvoiceLine.tax_amount).desc())
        )
        result = await self.session.execute(stmt)
        return [
            {
                "product_id": row.product_id,
                "product_name": row.product_name,
                "product_code": row.product_code or "",
                "qty_sold": Decimal(str(row.qty_sold)),
                "subtotal": Decimal(str(row.subtotal)),
                "tax_amount": Decimal(str(row.tax_amount)),
                "total": Decimal(str(row.total)),
            }
            for row in result.all()
        ]

    async def by_period(
        self, *, company_id: UUID, date_from: date, date_to: date
    ) -> list[dict]:
        """Aggregate invoiced sales grouped by calendar month."""
        # date_trunc('month', invoice_date) → first day of each month.
        # We use it as both the sort key and the period_start value.
        month_trunc = func.date_trunc("month", SalesInvoice.invoice_date)
        stmt = (
            select(
                month_trunc.label("period_start"),
                func.count(SalesInvoice.id).label("invoice_count"),
                func.coalesce(func.sum(SalesInvoice.subtotal_amount), 0).label("subtotal"),
                func.coalesce(func.sum(SalesInvoice.tax_amount), 0).label("tax_amount"),
                func.coalesce(func.sum(SalesInvoice.total_amount), 0).label("total"),
            )
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status.in_(_FINALIZED_STATUSES),
                SalesInvoice.invoice_type.in_(_FORWARD_INVOICE_TYPES),
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
            )
            .group_by(month_trunc)
            .order_by(month_trunc)
        )
        result = await self.session.execute(stmt)
        return [
            {
                # period_label: "2025-01" format — easy to read, sorts correctly
                "period_label": row.period_start.strftime("%Y-%m"),
                "period_start": row.period_start.date()
                if hasattr(row.period_start, "date")
                else row.period_start,
                "invoice_count": row.invoice_count,
                "subtotal": Decimal(str(row.subtotal)),
                "tax_amount": Decimal(str(row.tax_amount)),
                "total": Decimal(str(row.total)),
            }
            for row in result.all()
        ]
