"""Reporting services — Phase 8 §3: Reporting is the only module allowed to
read across other modules' repositories directly (read-only query
interfaces, not shared tables), since dashboards inherently aggregate
cross-module data (FR-RPT-003)."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.modules.accounting.infrastructure.repositories import JournalEntryRepository
from src.modules.commission.infrastructure.models import CommissionTransaction
from src.modules.identity.infrastructure.master_data_models import (
    Partner,
    Product,
    SalesRepresentative,
)
from src.modules.inventory.infrastructure.models import Location, StockLayer, StockQuant, Warehouse
from src.modules.payments.infrastructure.models import Payment, PaymentAllocation
from src.modules.payments.infrastructure.repositories import PaymentRepository
from src.modules.purchasing.infrastructure.models import PurchaseOrder, VendorBill
from src.modules.purchasing.infrastructure.repositories import (
    PurchaseOrderRepository,
    VendorBillRepository,
)
from src.modules.sales.infrastructure.models import (
    Quotation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
)
from src.modules.sales.infrastructure.repositories import SalesInvoiceRepository

ACCOUNT_CODE_AR = "1200"
ACCOUNT_CODE_AP = "2100"
ACCOUNT_CODE_CASH = "1100"


@dataclass(frozen=True)
class SalesTrendPoint:
    period_label: str
    total: Decimal


@dataclass(frozen=True)
class RecentActivityItem:
    entity_type: str
    entity_id: UUID
    label: str
    date: date
    amount: Decimal


@dataclass(frozen=True)
class DashboardSummary:
    period_start: date
    period_end: date
    period_sales_total: Decimal
    period_purchases_total: Decimal
    receivables_balance: Decimal
    payables_balance: Decimal
    cash_balance: Decimal
    sales_trend: list[SalesTrendPoint]
    pending_approvals_count: int
    recent_activity: list[RecentActivityItem]
    # Commercial Performance Stage 3 — "COMMERCIAL PERFORMANCE" dashboard
    # section. All zero/empty when commercial_service isn't wired (keeps
    # every pre-Stage-3 DashboardService caller/test working unchanged).
    commercial_total_sales: Decimal
    commercial_total_returns: Decimal
    commercial_net_sales: Decimal
    commercial_total_collections: Decimal
    commercial_sales_commission: Decimal
    commercial_collection_commission: Decimal
    commercial_net_commission: Decimal
    commercial_unattributed_sales: Decimal
    representative_performance: list[dict]
    collections_trend: list[SalesTrendPoint]


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


def _months_in_range(period_start: date, period_end: date) -> list[tuple[int, int]]:
    """[(year, month), ...] for every calendar month whose start falls
    within [period_start, period_end], oldest first. P0-8: replaces the
    old fixed "6 months trailing from today" window — the trend chart now
    spans exactly the caller's requested period (typically the company's
    current fiscal year to date), so the chart and the KPI cards above it
    always describe the same range instead of two different ones."""
    months = []
    y, m = period_start.year, period_start.month
    while date(y, m, 1) <= period_end:
        months.append((y, m))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return months


class DashboardService:
    """UI/UX Professional pass — Dashboard Enrichment (Product Owner audit:
    the dashboard was 4 static KPI cards, the single most visible gap
    against SAP B1/Dynamics 365 BC/Odoo/ERPNext, every one of which opens
    on a trend chart, an actionable exceptions list, and a recent-activity
    feed, not just numbers)."""

    def __init__(
        self,
        invoice_repo: SalesInvoiceRepository,
        bill_repo: VendorBillRepository,
        journal_entry_repo: JournalEntryRepository,
        order_repo: PurchaseOrderRepository | None = None,
        payment_repo: PaymentRepository | None = None,
        commercial_service: "CommercialPerformanceReportingService | None" = None,
    ):
        self.invoice_repo = invoice_repo
        self.bill_repo = bill_repo
        self.journal_entry_repo = journal_entry_repo
        self.order_repo = order_repo
        self.payment_repo = payment_repo
        self.commercial_service = commercial_service

    async def get_summary(self, *, company_id: UUID, period_start: date, period_end: date) -> DashboardSummary:
        sales_total = await self.invoice_repo.sum_total_in_range(company_id, period_start, period_end)
        purchases_total = await self.bill_repo.sum_total_in_range(company_id, period_start, period_end)
        # AR is a normal-debit account (asset): positive balance = amount owed to us.
        # Hardening fix: sums the whole 1200 subtree (root_code lookup), not just an
        # exact "1200" match — see account_balance_by_root_code's own docstring for why
        # an exact-code match silently misses activity once a company splits an account.
        ar_balance = await self.journal_entry_repo.account_balance_by_root_code(
            company_id, ACCOUNT_CODE_AR, period_end
        )
        # AP is a normal-credit account (liability): flip sign for a positive "amount we owe" figure.
        ap_balance = -(
            await self.journal_entry_repo.account_balance_by_root_code(company_id, ACCOUNT_CODE_AP, period_end)
        )
        # Cash and Bank is a normal-debit account (asset), same sign convention as AR.
        cash_balance = await self.journal_entry_repo.account_balance_by_root_code(
            company_id, ACCOUNT_CODE_CASH, period_end
        )

        return DashboardSummary(
            period_start=period_start,
            period_end=period_end,
            period_sales_total=sales_total,
            period_purchases_total=purchases_total,
            receivables_balance=ar_balance,
            payables_balance=ap_balance,
            cash_balance=cash_balance,
            sales_trend=await self._sales_trend(company_id, period_start, period_end),
            pending_approvals_count=await self._pending_approvals_count(company_id),
            recent_activity=await self._recent_activity(company_id),
            **await self._commercial_summary(company_id, period_start, period_end),
            collections_trend=await self._collections_trend(company_id, period_start, period_end),
        )

    async def _sales_trend(self, company_id: UUID, period_start: date, period_end: date) -> list[SalesTrendPoint]:
        points = []
        for year, month in _months_in_range(period_start, period_end):
            start, end = _month_bounds(year, month)
            total = await self.invoice_repo.sum_total_in_range(company_id, start, end)
            points.append(SalesTrendPoint(period_label=f"{year:04d}-{month:02d}", total=total))
        return points

    async def _collections_trend(self, company_id: UUID, period_start: date, period_end: date) -> list[SalesTrendPoint]:
        if self.payment_repo is None:
            return []
        points = []
        for year, month in _months_in_range(period_start, period_end):
            start, end = _month_bounds(year, month)
            total = await self.payment_repo.sum_customer_amount_in_range(company_id, start, end)
            points.append(SalesTrendPoint(period_label=f"{year:04d}-{month:02d}", total=total))
        return points

    async def _commercial_summary(self, company_id: UUID, period_start: date, period_end: date) -> dict:
        """Commercial Performance Stage 3 KPI cards, computed by summing
        the same `by_representative` rollup the Dashboard's own
        Representative Performance table uses — one query set, two
        consumers, never two different figures for the same period."""
        if self.commercial_service is None:
            return {
                "commercial_total_sales": Decimal("0"),
                "commercial_total_returns": Decimal("0"),
                "commercial_net_sales": Decimal("0"),
                "commercial_total_collections": Decimal("0"),
                "commercial_sales_commission": Decimal("0"),
                "commercial_collection_commission": Decimal("0"),
                "commercial_net_commission": Decimal("0"),
                "commercial_unattributed_sales": Decimal("0"),
                "representative_performance": [],
            }
        rows = await self.commercial_service.by_representative(
            company_id=company_id, date_from=period_start, date_to=period_end
        )
        unattributed = next((r["gross_sales"] for r in rows if r["is_unattributed"]), Decimal("0"))
        return {
            "commercial_total_sales": sum((r["gross_sales"] for r in rows), Decimal("0")),
            "commercial_total_returns": sum((r["returns"] for r in rows), Decimal("0")),
            "commercial_net_sales": sum((r["net_sales"] for r in rows), Decimal("0")),
            "commercial_total_collections": sum((r["collections"] for r in rows), Decimal("0")),
            "commercial_sales_commission": sum((r["sales_commission"] for r in rows), Decimal("0")),
            "commercial_collection_commission": sum((r["collection_commission"] for r in rows), Decimal("0")),
            "commercial_net_commission": sum((r["net_commission"] for r in rows), Decimal("0")),
            "commercial_unattributed_sales": unattributed,
            "representative_performance": rows,
        }

    async def _pending_approvals_count(self, company_id: UUID) -> int:
        if self.order_repo is None:
            return 0
        pending = await self.order_repo.list_by_company(company_id, status="pending_approval")
        return len(pending)

    async def _recent_activity(self, company_id: UUID, *, limit: int = 8) -> list[RecentActivityItem]:
        items: list[RecentActivityItem] = []

        invoices = await self.invoice_repo.list_by_company(company_id, limit=limit)
        items.extend(
            RecentActivityItem(
                entity_type="sales_invoice",
                entity_id=inv.id,
                label=inv.number,
                date=inv.invoice_date,
                amount=inv.total_amount,
            )
            for inv in invoices
        )

        if self.order_repo is not None:
            orders = await self.order_repo.list_by_company(company_id)
            for order in orders[:limit]:
                items.append(
                    RecentActivityItem(
                        entity_type="purchase_order",
                        entity_id=order.id,
                        label=order.number,
                        date=order.order_date,
                        amount=order.total_amount,
                    )
                )

        if self.payment_repo is not None:
            payments = await self.payment_repo.list_by_company(company_id, limit=limit)
            items.extend(
                RecentActivityItem(
                    entity_type="payment",
                    entity_id=p.id,
                    label=p.number,
                    date=p.payment_date,
                    amount=p.amount,
                )
                for p in payments
            )

        items.sort(key=lambda i: i.date, reverse=True)
        return items[:limit]


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
        """Aggregate invoiced sales grouped by customer (partner), plus
        payments received in the same period and the customer's running
        balance as of date_to (Owner-requested: this report showed sales
        only, with no way to see it next to what was actually collected
        and what's still owed — which is exactly what caused a live
        "these numbers don't match" report, since the period sales figure
        here was never meant to equal the Trial Balance's cumulative AR
        balance)."""
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
        rows = [
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
        if not rows:
            return rows

        partner_ids = [r["partner_id"] for r in rows]
        payments_by_partner = await self._payments_received(
            company_id=company_id, partner_ids=partner_ids, date_from=date_from, date_to=date_to
        )
        balance_by_partner = await self._ar_balance_as_of(
            company_id=company_id, partner_ids=partner_ids, as_of_date=date_to
        )
        for r in rows:
            r["payments_received"] = payments_by_partner.get(r["partner_id"], Decimal("0"))
            r["balance"] = balance_by_partner.get(r["partner_id"], Decimal("0"))
        return rows

    async def _payments_received(
        self, *, company_id: UUID, partner_ids: list[UUID], date_from: date, date_to: date
    ) -> dict[UUID, Decimal]:
        stmt = (
            select(Payment.partner_id, func.coalesce(func.sum(Payment.amount), 0).label("total"))
            .where(
                Payment.company_id == company_id,
                Payment.payment_type == "customer",
                Payment.partner_id.in_(partner_ids),
                Payment.payment_date >= date_from,
                Payment.payment_date <= date_to,
            )
            .group_by(Payment.partner_id)
        )
        result = await self.session.execute(stmt)
        return {row.partner_id: Decimal(str(row.total)) for row in result.all()}

    async def _ar_balance_as_of(
        self, *, company_id: UUID, partner_ids: list[UUID], as_of_date: date
    ) -> dict[UUID, Decimal]:
        """Cumulative balance per customer as of as_of_date: every posted
        invoice ever issued (credit notes as a negative, since they carry
        the same partner_id as the customer they were issued against) minus
        every payment ever received — matching the exact figure the Trial
        Balance's Accounts Receivable would show, unlike `total` above
        which is scoped to [date_from, date_to]."""
        invoiced_stmt = (
            select(
                SalesInvoice.partner_id,
                func.coalesce(
                    func.sum(
                        case(
                            (SalesInvoice.invoice_type == "credit_note", -SalesInvoice.total_amount),
                            else_=SalesInvoice.total_amount,
                        )
                    ),
                    0,
                ).label("net_invoiced"),
            )
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.partner_id.in_(partner_ids),
                SalesInvoice.journal_entry_id.isnot(None),
                SalesInvoice.invoice_date <= as_of_date,
            )
            .group_by(SalesInvoice.partner_id)
        )
        paid_stmt = (
            select(Payment.partner_id, func.coalesce(func.sum(Payment.amount), 0).label("total"))
            .where(
                Payment.company_id == company_id,
                Payment.payment_type == "customer",
                Payment.partner_id.in_(partner_ids),
                Payment.payment_date <= as_of_date,
            )
            .group_by(Payment.partner_id)
        )
        invoiced_result = await self.session.execute(invoiced_stmt)
        paid_result = await self.session.execute(paid_stmt)
        net_invoiced = {row.partner_id: Decimal(str(row.net_invoiced)) for row in invoiced_result.all()}
        paid = {row.partner_id: Decimal(str(row.total)) for row in paid_result.all()}
        return {
            partner_id: net_invoiced.get(partner_id, Decimal("0")) - paid.get(partner_id, Decimal("0"))
            for partner_id in partner_ids
        }

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


class CommercialPerformanceReportingService:
    """Commercial Performance Stage 3 — sales-rep / collection-rep
    performance and commission reporting (Dashboard section, "By
    Representative" report, and the Representative Performance drill-down).

    Follows `SalesReportingService`'s exact "group, then batch-fetch
    related aggregates" pattern: one grouped query per metric, merged in
    Python by representative_id — never N+1 per row. A `None` group key
    means "no sales_rep_id / collection_rep_id attributed" (legacy data
    predating Stage 2B/2D, or a genuinely unattributed transaction) and is
    surfaced explicitly as "Unattributed / Legacy", never silently dropped
    or merged into any real representative's figures (Stage 3 Part J)."""

    UNATTRIBUTED_LABEL = "Unattributed / Legacy"

    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_representative(
        self,
        *,
        company_id: UUID,
        date_from: date,
        date_to: date,
        representative_id: UUID | None = None,
    ) -> list[dict]:
        gross = await self._gross_sales_by_rep(company_id, date_from, date_to)
        returns = await self._returns_by_rep(company_id, date_from, date_to)
        collections = await self._collections_by_rep(company_id, date_from, date_to)
        sales_comm = await self._commission_by_rep(company_id, date_from, date_to, "sales")
        collection_comm = await self._commission_by_rep(company_id, date_from, date_to, "collection")
        outstanding = await self._outstanding_balance_by_rep(company_id, as_of_date=date_to)

        rep_result = await self.session.execute(
            select(SalesRepresentative.id, SalesRepresentative.name, SalesRepresentative.is_active).where(
                SalesRepresentative.company_id == company_id
            )
        )
        rep_info = {row.id: (row.name, row.is_active) for row in rep_result.all()}

        # Every rep still currently active is shown even with zero activity
        # (management visibility into idle reps); any rep — active or
        # archived — with real activity in the period is shown by name; the
        # `None` key (no rep attributed) is surfaced only when there is
        # genuinely unattributed activity, never fabricated.
        activity_ids = (
            set(gross) | set(returns) | set(collections) | set(sales_comm) | set(collection_comm) | set(outstanding)
        )
        active_rep_ids = {rid for rid, (_, active) in rep_info.items() if active}
        ids = activity_ids | active_rep_ids
        if representative_id is not None:
            ids = {representative_id} if representative_id in ids or representative_id in rep_info else set()

        rows = []
        for rid in ids:
            g = gross.get(rid, {"invoice_count": 0, "gross": Decimal("0"), "customer_count": 0})
            gross_sales = g["gross"]
            returns_amt = returns.get(rid, Decimal("0"))
            invoice_count = g["invoice_count"]
            avg_invoice = (gross_sales / invoice_count) if invoice_count else Decimal("0")
            sales_commission = sales_comm.get(rid, Decimal("0"))
            collection_commission = collection_comm.get(rid, Decimal("0"))
            rows.append(
                {
                    "representative_id": rid,
                    "representative_name": rep_info[rid][0] if rid in rep_info else self.UNATTRIBUTED_LABEL,
                    "is_unattributed": rid is None,
                    "gross_sales": gross_sales,
                    "returns": returns_amt,
                    "net_sales": gross_sales - returns_amt,
                    "invoice_count": invoice_count,
                    "customer_count": g["customer_count"],
                    "average_invoice_value": avg_invoice,
                    "collections": collections.get(rid, Decimal("0")),
                    "outstanding_balance": outstanding.get(rid, Decimal("0")),
                    "sales_commission": sales_commission,
                    "collection_commission": collection_commission,
                    "net_commission": sales_commission + collection_commission,
                }
            )
        rows.sort(key=lambda r: r["net_sales"], reverse=True)
        return rows

    async def representative_customers(
        self, *, company_id: UUID, representative_id: UUID, date_from: date, date_to: date
    ) -> list[dict]:
        """Drill-down level 2 (Representative -> Customer): per-customer
        rollup restricted to this representative's own sales attribution."""
        stmt = (
            select(
                Partner.id.label("partner_id"),
                Partner.name.label("partner_name"),
                func.count(SalesInvoice.id).label("invoice_count"),
                func.coalesce(func.sum(SalesInvoice.subtotal_amount), 0).label("gross"),
            )
            .join(Partner, Partner.id == SalesInvoice.partner_id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.sales_rep_id == representative_id,
                SalesInvoice.status.in_(_FINALIZED_STATUSES),
                SalesInvoice.invoice_type.in_(_FORWARD_INVOICE_TYPES),
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
            )
            .group_by(Partner.id, Partner.name)
            .order_by(func.sum(SalesInvoice.subtotal_amount).desc())
        )
        result = await self.session.execute(stmt)
        rows = [
            {
                "partner_id": row.partner_id,
                "partner_name": row.partner_name,
                "invoice_count": row.invoice_count,
                "gross_sales": Decimal(str(row.gross)),
            }
            for row in result.all()
        ]
        if not rows:
            return rows

        partner_ids = [r["partner_id"] for r in rows]
        returns_stmt = (
            select(
                SalesInvoice.partner_id, func.coalesce(func.sum(SalesInvoice.subtotal_amount), 0).label("returns")
            )
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.sales_rep_id == representative_id,
                SalesInvoice.invoice_type == "credit_note",
                SalesInvoice.partner_id.in_(partner_ids),
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
            )
            .group_by(SalesInvoice.partner_id)
        )
        returns_result = await self.session.execute(returns_stmt)
        returns_by_partner = {row.partner_id: Decimal(str(row.returns)) for row in returns_result.all()}
        for r in rows:
            returns_amt = returns_by_partner.get(r["partner_id"], Decimal("0"))
            r["returns"] = returns_amt
            r["net_sales"] = r["gross_sales"] - returns_amt
            r["average_invoice_value"] = (
                (r["gross_sales"] / r["invoice_count"]) if r["invoice_count"] else Decimal("0")
            )
        return rows

    async def representative_performance(
        self, *, company_id: UUID, representative_id: UUID, date_from: date, date_to: date
    ) -> dict:
        """Drill-down detail report (Stage 3 Part C): the rep's own summary
        row plus the three line-item sections, each carrying the historical
        commission_rate/commission_amount actually recorded at the time
        (never recomputed from today's rate)."""
        summary_rows = await self.by_representative(
            company_id=company_id, date_from=date_from, date_to=date_to, representative_id=representative_id
        )
        summary = summary_rows[0] if summary_rows else None

        original_invoice = aliased(SalesInvoice)
        sales_commission_txn = aliased(CommissionTransaction)
        returns_commission_txn = aliased(CommissionTransaction)
        collections_commission_txn = aliased(CommissionTransaction)

        sales_stmt = (
            select(
                SalesInvoice.id,
                SalesInvoice.number,
                SalesInvoice.invoice_date,
                Partner.name.label("partner_name"),
                SalesInvoice.subtotal_amount,
                sales_commission_txn.commission_rate,
                sales_commission_txn.commission_amount,
            )
            .join(Partner, Partner.id == SalesInvoice.partner_id)
            .outerjoin(
                sales_commission_txn,
                (sales_commission_txn.source_table == "sales_invoice")
                & (sales_commission_txn.source_id == SalesInvoice.id)
                & (sales_commission_txn.commission_type == "sales"),
            )
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.sales_rep_id == representative_id,
                SalesInvoice.status.in_(_FINALIZED_STATUSES),
                SalesInvoice.invoice_type.in_(_FORWARD_INVOICE_TYPES),
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
            )
            .order_by(SalesInvoice.invoice_date)
        )
        sales_result = await self.session.execute(sales_stmt)
        sales_lines = [
            {
                "invoice_id": row.id,
                "invoice_number": row.number,
                "invoice_date": row.invoice_date,
                "customer_name": row.partner_name,
                "sales_amount": Decimal(str(row.subtotal_amount)),
                "commission_rate": Decimal(str(row.commission_rate)) if row.commission_rate is not None else None,
                "commission_amount": (
                    Decimal(str(row.commission_amount)) if row.commission_amount is not None else Decimal("0")
                ),
            }
            for row in sales_result.all()
        ]

        returns_stmt = (
            select(
                SalesInvoice.id,
                SalesInvoice.number,
                SalesInvoice.invoice_date,
                Partner.name.label("partner_name"),
                original_invoice.number.label("original_invoice_number"),
                SalesInvoice.subtotal_amount,
                returns_commission_txn.commission_rate,
                returns_commission_txn.commission_amount,
            )
            .join(Partner, Partner.id == SalesInvoice.partner_id)
            .outerjoin(original_invoice, original_invoice.id == SalesInvoice.original_invoice_id)
            .outerjoin(
                returns_commission_txn,
                (returns_commission_txn.source_table == "sales_invoice")
                & (returns_commission_txn.source_id == SalesInvoice.id)
                & (returns_commission_txn.commission_type == "sales"),
            )
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.sales_rep_id == representative_id,
                SalesInvoice.invoice_type == "credit_note",
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
            )
            .order_by(SalesInvoice.invoice_date)
        )
        returns_result = await self.session.execute(returns_stmt)
        returns_lines = [
            {
                "credit_note_id": row.id,
                "credit_note_number": row.number,
                "credit_note_date": row.invoice_date,
                "customer_name": row.partner_name,
                "original_invoice_number": row.original_invoice_number,
                "return_amount": Decimal(str(row.subtotal_amount)),
                "commission_rate": Decimal(str(row.commission_rate)) if row.commission_rate is not None else None,
                "commission_amount": (
                    Decimal(str(row.commission_amount)) if row.commission_amount is not None else Decimal("0")
                ),
            }
            for row in returns_result.all()
        ]

        collections_stmt = (
            select(
                Payment.id,
                Payment.number,
                Payment.payment_date,
                Partner.name.label("partner_name"),
                Payment.amount,
                collections_commission_txn.commission_rate,
                collections_commission_txn.commission_amount,
            )
            .join(Partner, Partner.id == Payment.partner_id)
            .outerjoin(
                collections_commission_txn,
                (collections_commission_txn.source_table == "payment")
                & (collections_commission_txn.source_id == Payment.id)
                & (collections_commission_txn.commission_type == "collection"),
            )
            .where(
                Payment.company_id == company_id,
                Payment.collection_rep_id == representative_id,
                Payment.payment_type == "customer",
                Payment.payment_date >= date_from,
                Payment.payment_date <= date_to,
            )
            .order_by(Payment.payment_date)
        )
        collections_result = await self.session.execute(collections_stmt)
        collections_lines = [
            {
                "payment_id": row.id,
                "payment_number": row.number,
                "payment_date": row.payment_date,
                "customer_name": row.partner_name,
                "collection_amount": Decimal(str(row.amount)),
                "commission_rate": Decimal(str(row.commission_rate)) if row.commission_rate is not None else None,
                "commission_amount": (
                    Decimal(str(row.commission_amount)) if row.commission_amount is not None else Decimal("0")
                ),
            }
            for row in collections_result.all()
        ]

        return {
            "summary": summary,
            "sales_lines": sales_lines,
            "returns_lines": returns_lines,
            "collections_lines": collections_lines,
        }

    async def _gross_sales_by_rep(self, company_id: UUID, date_from: date, date_to: date) -> dict:
        stmt = (
            select(
                SalesInvoice.sales_rep_id,
                func.count(SalesInvoice.id).label("invoice_count"),
                func.coalesce(func.sum(SalesInvoice.subtotal_amount), 0).label("gross"),
                func.count(func.distinct(SalesInvoice.partner_id)).label("customer_count"),
            )
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status.in_(_FINALIZED_STATUSES),
                SalesInvoice.invoice_type.in_(_FORWARD_INVOICE_TYPES),
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
            )
            .group_by(SalesInvoice.sales_rep_id)
        )
        result = await self.session.execute(stmt)
        return {
            row.sales_rep_id: {
                "invoice_count": row.invoice_count,
                "gross": Decimal(str(row.gross)),
                "customer_count": row.customer_count,
            }
            for row in result.all()
        }

    async def _returns_by_rep(self, company_id: UUID, date_from: date, date_to: date) -> dict[UUID | None, Decimal]:
        stmt = (
            select(
                SalesInvoice.sales_rep_id, func.coalesce(func.sum(SalesInvoice.subtotal_amount), 0).label("returns")
            )
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.status.in_(_FINALIZED_STATUSES),
                SalesInvoice.invoice_type == "credit_note",
                SalesInvoice.invoice_date >= date_from,
                SalesInvoice.invoice_date <= date_to,
            )
            .group_by(SalesInvoice.sales_rep_id)
        )
        result = await self.session.execute(stmt)
        return {row.sales_rep_id: Decimal(str(row.returns)) for row in result.all()}

    async def _collections_by_rep(
        self, company_id: UUID, date_from: date, date_to: date
    ) -> dict[UUID | None, Decimal]:
        stmt = (
            select(Payment.collection_rep_id, func.coalesce(func.sum(Payment.amount), 0).label("total"))
            .where(
                Payment.company_id == company_id,
                Payment.payment_type == "customer",
                Payment.payment_date >= date_from,
                Payment.payment_date <= date_to,
            )
            .group_by(Payment.collection_rep_id)
        )
        result = await self.session.execute(stmt)
        return {row.collection_rep_id: Decimal(str(row.total)) for row in result.all()}

    async def _commission_by_rep(
        self, company_id: UUID, date_from: date, date_to: date, commission_type: str
    ) -> dict[UUID, Decimal]:
        stmt = (
            select(
                CommissionTransaction.representative_id,
                func.coalesce(func.sum(CommissionTransaction.commission_amount), 0).label("total"),
            )
            .where(
                CommissionTransaction.company_id == company_id,
                CommissionTransaction.commission_type == commission_type,
                CommissionTransaction.transaction_date >= date_from,
                CommissionTransaction.transaction_date <= date_to,
            )
            .group_by(CommissionTransaction.representative_id)
        )
        result = await self.session.execute(stmt)
        return {row.representative_id: Decimal(str(row.total)) for row in result.all()}

    async def _outstanding_balance_by_rep(self, company_id: UUID, *, as_of_date: date) -> dict[UUID | None, Decimal]:
        """Point-in-time (not period-bound) balance attributable to each
        rep's own sales attribution, as of as_of_date — mirrors
        SalesReportingService._ar_balance_as_of's net-invoiced-minus-paid
        approach, grouped by sales_rep_id instead of partner_id."""
        invoiced_stmt = (
            select(
                SalesInvoice.sales_rep_id,
                func.coalesce(
                    func.sum(
                        case(
                            (SalesInvoice.invoice_type == "credit_note", -SalesInvoice.total_amount),
                            else_=SalesInvoice.total_amount,
                        )
                    ),
                    0,
                ).label("net_invoiced"),
            )
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.journal_entry_id.isnot(None),
                SalesInvoice.invoice_date <= as_of_date,
            )
            .group_by(SalesInvoice.sales_rep_id)
        )
        paid_stmt = (
            select(
                SalesInvoice.sales_rep_id,
                func.coalesce(func.sum(PaymentAllocation.amount), 0).label("total"),
            )
            .select_from(PaymentAllocation)
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .join(SalesInvoice, SalesInvoice.id == PaymentAllocation.sales_invoice_id)
            .where(Payment.company_id == company_id, Payment.payment_date <= as_of_date)
            .group_by(SalesInvoice.sales_rep_id)
        )
        invoiced_result = await self.session.execute(invoiced_stmt)
        paid_result = await self.session.execute(paid_stmt)
        net_invoiced = {row.sales_rep_id: Decimal(str(row.net_invoiced)) for row in invoiced_result.all()}
        paid = {row.sales_rep_id: Decimal(str(row.total)) for row in paid_result.all()}
        ids = set(net_invoiced) | set(paid)
        return {rid: net_invoiced.get(rid, Decimal("0")) - paid.get(rid, Decimal("0")) for rid in ids}


# The one state where a VendorBill has actually posted a Journal Entry
# (approve_and_post and issue_debit_note both set status="posted" in the
# same transaction they post the JE) -- the direct equivalent of
# SalesInvoice's journal_entry_id.isnot(None) checks above, just expressed
# as the status value since Purchasing's finalized state is a single value
# rather than sales' multi-value _FINALIZED_STATUSES.
_FINALIZED_BILL_STATUS = "posted"


class PurchaseReportingService:
    """P0-3 (3-Day Brief): Purchasing's mirror of SalesReportingService.by_customer
    -- same shape (vendor, invoice count, amount/VAT/total, running balance),
    plus an Adjustments/Net Purchases pair the sales report doesn't have,
    since the brief explicitly asked for debit notes to show as their own
    column here rather than just silently netting into balance."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_vendor(
        self,
        *,
        company_id: UUID,
        date_from: date,
        date_to: date,
        partner_id: UUID | None = None,
    ) -> list[dict]:
        conditions = [
            VendorBill.company_id == company_id,
            VendorBill.status == _FINALIZED_BILL_STATUS,
            VendorBill.bill_type == "standard",
            VendorBill.bill_date >= date_from,
            VendorBill.bill_date <= date_to,
        ]
        if partner_id is not None:
            conditions.append(VendorBill.partner_id == partner_id)

        stmt = (
            select(
                Partner.id.label("partner_id"),
                Partner.name.label("partner_name"),
                func.count(VendorBill.id).label("bill_count"),
                func.coalesce(func.sum(VendorBill.subtotal_amount), 0).label("subtotal"),
                func.coalesce(func.sum(VendorBill.tax_amount), 0).label("tax_amount"),
                func.coalesce(func.sum(VendorBill.total_amount), 0).label("total"),
            )
            .join(Partner, Partner.id == VendorBill.partner_id)
            .where(*conditions)
            .group_by(Partner.id, Partner.name)
            .order_by(func.sum(VendorBill.total_amount).desc())
        )
        result = await self.session.execute(stmt)
        rows = [
            {
                "partner_id": row.partner_id,
                "partner_name": row.partner_name,
                "bill_count": row.bill_count,
                "subtotal": Decimal(str(row.subtotal)),
                "tax_amount": Decimal(str(row.tax_amount)),
                "total": Decimal(str(row.total)),
            }
            for row in result.all()
        ]
        if not rows:
            return rows

        partner_ids = [r["partner_id"] for r in rows]
        adjustments_by_partner = await self._adjustments_in_period(
            company_id=company_id, partner_ids=partner_ids, date_from=date_from, date_to=date_to
        )
        payments_by_partner = await self._payments_made(
            company_id=company_id, partner_ids=partner_ids, date_from=date_from, date_to=date_to
        )
        balance_by_partner = await self._ap_balance_as_of(
            company_id=company_id, partner_ids=partner_ids, as_of_date=date_to
        )
        for r in rows:
            adjustments = adjustments_by_partner.get(r["partner_id"], Decimal("0"))
            r["adjustments"] = adjustments
            r["net_total"] = r["total"] - adjustments
            r["payments_made"] = payments_by_partner.get(r["partner_id"], Decimal("0"))
            r["balance"] = balance_by_partner.get(r["partner_id"], Decimal("0"))
        return rows

    async def _adjustments_in_period(
        self, *, company_id: UUID, partner_ids: list[UUID], date_from: date, date_to: date
    ) -> dict[UUID, Decimal]:
        """Debit notes issued against this vendor in [date_from, date_to] --
        shown as its own column (not silently folded into `total`), same
        reasoning the Owner gave for adding payments/balance to the sales
        report: a number you can't see is a number you can't trust."""
        stmt = (
            select(VendorBill.partner_id, func.coalesce(func.sum(VendorBill.total_amount), 0).label("total"))
            .where(
                VendorBill.company_id == company_id,
                VendorBill.bill_type == "debit_note",
                VendorBill.partner_id.in_(partner_ids),
                VendorBill.bill_date >= date_from,
                VendorBill.bill_date <= date_to,
            )
            .group_by(VendorBill.partner_id)
        )
        result = await self.session.execute(stmt)
        return {row.partner_id: Decimal(str(row.total)) for row in result.all()}

    async def _payments_made(
        self, *, company_id: UUID, partner_ids: list[UUID], date_from: date, date_to: date
    ) -> dict[UUID, Decimal]:
        stmt = (
            select(Payment.partner_id, func.coalesce(func.sum(Payment.amount), 0).label("total"))
            .where(
                Payment.company_id == company_id,
                Payment.payment_type == "vendor",
                Payment.partner_id.in_(partner_ids),
                Payment.payment_date >= date_from,
                Payment.payment_date <= date_to,
            )
            .group_by(Payment.partner_id)
        )
        result = await self.session.execute(stmt)
        return {row.partner_id: Decimal(str(row.total)) for row in result.all()}

    async def _ap_balance_as_of(
        self, *, company_id: UUID, partner_ids: list[UUID], as_of_date: date
    ) -> dict[UUID, Decimal]:
        """Cumulative balance per vendor as of as_of_date -- every posted
        bill ever billed (debit notes as a negative) minus every payment
        ever made, matching the exact figure the Trial Balance's Accounts
        Payable would show. Mirrors _ar_balance_as_of exactly, direction
        reversed."""
        billed_stmt = (
            select(
                VendorBill.partner_id,
                func.coalesce(
                    func.sum(
                        case(
                            (VendorBill.bill_type == "debit_note", -VendorBill.total_amount),
                            else_=VendorBill.total_amount,
                        )
                    ),
                    0,
                ).label("net_billed"),
            )
            .where(
                VendorBill.company_id == company_id,
                VendorBill.partner_id.in_(partner_ids),
                VendorBill.journal_entry_id.isnot(None),
                VendorBill.bill_date <= as_of_date,
            )
            .group_by(VendorBill.partner_id)
        )
        paid_stmt = (
            select(Payment.partner_id, func.coalesce(func.sum(Payment.amount), 0).label("total"))
            .where(
                Payment.company_id == company_id,
                Payment.payment_type == "vendor",
                Payment.partner_id.in_(partner_ids),
                Payment.payment_date <= as_of_date,
            )
            .group_by(Payment.partner_id)
        )
        billed_result = await self.session.execute(billed_stmt)
        paid_result = await self.session.execute(paid_stmt)
        net_billed = {row.partner_id: Decimal(str(row.net_billed)) for row in billed_result.all()}
        paid = {row.partner_id: Decimal(str(row.total)) for row in paid_result.all()}
        return {
            partner_id: net_billed.get(partner_id, Decimal("0")) - paid.get(partner_id, Decimal("0"))
            for partner_id in partner_ids
        }


class SearchService:
    """Professional Workspace Layer — Global Search. Every reference ERP
    has a single search box that crosses entity types instead of making
    the user already know which module a customer/invoice/product lives
    in; this system had none. Read-only, cross-module — same rule as the
    rest of this file (Reporting is the one module allowed to query other
    modules' tables directly). RLS still fully applies per-table (each
    query is `company_id`-scoped), so this can't leak cross-company data
    even though it isn't gated per-entity-type like a full permission
    model would be — a coarse `search.use` permission is the gate, matching
    the `audit_log.view`-style "one permission for a cross-cutting concern"
    precedent already used elsewhere in this codebase."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(self, *, company_id: UUID, query: str, limit_per_type: int = 5) -> list[dict]:
        pattern = f"%{query}%"
        results: list[dict] = []

        partner_rows = await self.session.execute(
            select(Partner.id, Partner.name, Partner.email)
            .where(
                Partner.company_id == company_id,
                Partner.deleted_at.is_(None),
                or_(Partner.name.ilike(pattern), Partner.name_ar.ilike(pattern)),
            )
            .order_by(Partner.name)
            .limit(limit_per_type)
        )
        results += [
            {"type": "partner", "id": r.id, "label": r.name, "sublabel": r.email}
            for r in partner_rows.all()
        ]

        product_rows = await self.session.execute(
            select(Product.id, Product.name, Product.sku)
            .where(
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
                or_(Product.name.ilike(pattern), Product.sku.ilike(pattern)),
            )
            .order_by(Product.name)
            .limit(limit_per_type)
        )
        results += [
            {"type": "product", "id": r.id, "label": r.name, "sublabel": r.sku}
            for r in product_rows.all()
        ]

        for model, type_name in (
            (Quotation, "sales_quotation"),
            (SalesOrder, "sales_order"),
            (SalesInvoice, "sales_invoice"),
            (PurchaseOrder, "purchase_order"),
            (VendorBill, "vendor_bill"),
        ):
            rows = await self.session.execute(
                select(model.id, model.number, model.status)
                .where(model.company_id == company_id, model.number.ilike(pattern))
                .order_by(model.number)
                .limit(limit_per_type)
            )
            results += [
                {"type": type_name, "id": r.id, "label": r.number, "sublabel": r.status}
                for r in rows.all()
            ]

        return results


ACCOUNT_CODE_VAT_PAYABLE = "2200"
# Same small, fixed, explicit tolerance as Inventory/Fixed Assets
# reconciliation — large enough to absorb genuinely unavoidable
# sub-cent rounding, never large enough to mask a real gap.
VAT_RECONCILIATION_TOLERANCE = Decimal("1.00")


class VatReportingService:
    """VAT/Tax Summary — explicitly named in the Owner's original Bundle E
    spec, and the standard baseline every Saudi business needs before
    filing a ZATCA VAT return: output VAT collected on sales vs. input VAT
    paid on purchases for a period, netted to what's actually owed (or
    refundable). Only counts documents that have actually posted to the
    books (`journal_entry_id is not None`) — the same "real accounting
    impact, not just a draft" filter AR/AP Aging already applies."""

    def __init__(self, session: AsyncSession, journal_entry_repo: JournalEntryRepository | None = None):
        self.session = session
        # Optional so existing call sites/tests building this service
        # without a journal_entry_repo (vat_summary/vat_detail never
        # needed one) keep working unchanged — only get_reconciliation
        # uses it, same precedent as InventoryValuationReportService.
        self.journal_entry_repo = journal_entry_repo

    async def vat_summary(self, *, company_id: UUID, date_from: date, date_to: date) -> dict:
        sales_stmt = select(
            func.coalesce(func.sum(SalesInvoice.subtotal_amount), 0).label("subtotal"),
            func.coalesce(func.sum(SalesInvoice.tax_amount), 0).label("vat"),
            func.coalesce(func.sum(SalesInvoice.total_amount), 0).label("total"),
        ).where(
            SalesInvoice.company_id == company_id,
            SalesInvoice.journal_entry_id.is_not(None),
            SalesInvoice.invoice_type.in_(_FORWARD_INVOICE_TYPES),
            SalesInvoice.invoice_date >= date_from,
            SalesInvoice.invoice_date <= date_to,
        )
        credit_note_stmt = select(
            func.coalesce(func.sum(SalesInvoice.subtotal_amount), 0).label("subtotal"),
            func.coalesce(func.sum(SalesInvoice.tax_amount), 0).label("vat"),
            func.coalesce(func.sum(SalesInvoice.total_amount), 0).label("total"),
        ).where(
            SalesInvoice.company_id == company_id,
            SalesInvoice.journal_entry_id.is_not(None),
            SalesInvoice.invoice_type == "credit_note",
            SalesInvoice.invoice_date >= date_from,
            SalesInvoice.invoice_date <= date_to,
        )
        # Dashboard-bug sibling fix (2026-08-19): this query used to sum
        # every posted VendorBill regardless of `bill_type`, so a Vendor
        # Debit Note (bill_type="debit_note", a return to the vendor
        # stored with the same positive amount as the bill it reverses)
        # was being ADDED to input VAT/purchases instead of netted out --
        # the same defect found in the Dashboard's purchases KPI
        # (VendorBillRepository.sum_total_in_range). That fix excluded
        # debit notes from `purchases_stmt` entirely (`bill_type ==
        # "standard"`) rather than actually mirroring the sales side's own
        # convention as its own comment claimed -- credit notes on the
        # sales side are NOT excluded, they're queried separately and
        # SUBTRACTED (`output_vat = sales_row.vat - credit_row.vat`).
        # Excluding debit notes outright stops the double-count but
        # silently drops their real VAT reversal from the figure, which
        # `issue_debit_note`'s own JE always posts to the GL's VAT
        # account regardless -- a second real, reported gap (Trial
        # Balance's VAT Payable vs this report, SAR 16,822,500 on a real
        # company) from the exact same root cause as the double-count fix
        # was meant to close, just the opposite direction of the same
        # asymmetry. Netting debit notes here the same way credit notes
        # already are closes both.
        purchases_stmt = select(
            func.coalesce(func.sum(VendorBill.subtotal_amount), 0).label("subtotal"),
            func.coalesce(func.sum(VendorBill.tax_amount), 0).label("vat"),
            func.coalesce(func.sum(VendorBill.total_amount), 0).label("total"),
        ).where(
            VendorBill.company_id == company_id,
            VendorBill.journal_entry_id.is_not(None),
            VendorBill.bill_type == "standard",
            VendorBill.bill_date >= date_from,
            VendorBill.bill_date <= date_to,
        )
        debit_note_stmt = select(
            func.coalesce(func.sum(VendorBill.subtotal_amount), 0).label("subtotal"),
            func.coalesce(func.sum(VendorBill.tax_amount), 0).label("vat"),
            func.coalesce(func.sum(VendorBill.total_amount), 0).label("total"),
        ).where(
            VendorBill.company_id == company_id,
            VendorBill.journal_entry_id.is_not(None),
            VendorBill.bill_type == "debit_note",
            VendorBill.bill_date >= date_from,
            VendorBill.bill_date <= date_to,
        )

        sales_row = (await self.session.execute(sales_stmt)).one()
        credit_row = (await self.session.execute(credit_note_stmt)).one()
        purchases_row = (await self.session.execute(purchases_stmt)).one()
        debit_row = (await self.session.execute(debit_note_stmt)).one()

        sales_subtotal = Decimal(str(sales_row.subtotal)) - Decimal(str(credit_row.subtotal))
        output_vat = Decimal(str(sales_row.vat)) - Decimal(str(credit_row.vat))
        sales_total = Decimal(str(sales_row.total)) - Decimal(str(credit_row.total))
        purchases_subtotal = Decimal(str(purchases_row.subtotal)) - Decimal(str(debit_row.subtotal))
        input_vat = Decimal(str(purchases_row.vat)) - Decimal(str(debit_row.vat))
        purchases_total = Decimal(str(purchases_row.total)) - Decimal(str(debit_row.total))

        return {
            "sales_subtotal": sales_subtotal,
            "output_vat": output_vat,
            "sales_total": sales_total,
            "purchases_subtotal": purchases_subtotal,
            "input_vat": input_vat,
            "purchases_total": purchases_total,
            "net_vat_payable": output_vat - input_vat,
        }

    async def vat_detail(self, *, company_id: UUID, date_from: date, date_to: date) -> list[dict]:
        """Per-document breakdown behind `vat_summary` -- every posted sales
        invoice, sales credit note, vendor bill, and vendor debit note in
        the period, so the Owner can trace the net VAT payable figure back
        to the individual documents that make it up rather than trusting a
        single netted number. Same document scope as `vat_summary` (both
        net debit/credit notes against their forward counterparts rather
        than excluding either side -- see that method's docstring for the
        real reconciliation gap excluding debit notes caused). Credit
        notes and debit notes both carry negated amounts (same contra
        convention `vat_summary` already applies when subtracting
        `credit_row`/`debit_row` from `sales_row`/`purchases_row`), so
        summing any column here reproduces the exact totals `vat_summary`
        returns."""

        async def _rows(model, date_column, type_filter, movement_type: str, direction: str, negate: bool):
            stmt = (
                select(
                    model.id,
                    model.number,
                    date_column.label("doc_date"),
                    Partner.name.label("partner_name"),
                    model.subtotal_amount,
                    model.tax_amount,
                    model.total_amount,
                )
                .join(Partner, Partner.id == model.partner_id)
                .where(
                    model.company_id == company_id,
                    model.journal_entry_id.is_not(None),
                    type_filter,
                    date_column >= date_from,
                    date_column <= date_to,
                )
                .order_by(date_column, model.number)
            )
            result = await self.session.execute(stmt)
            sign = Decimal("-1") if negate else Decimal("1")
            return [
                {
                    "document_date": r.doc_date,
                    "movement_type": movement_type,
                    "direction": direction,
                    "document_id": r.id,
                    "number": r.number,
                    "partner_name": r.partner_name,
                    "subtotal_amount": Decimal(str(r.subtotal_amount)) * sign,
                    "vat_amount": Decimal(str(r.tax_amount)) * sign,
                    "total_amount": Decimal(str(r.total_amount)) * sign,
                }
                for r in result.all()
            ]

        invoice_rows = await _rows(
            SalesInvoice, SalesInvoice.invoice_date, SalesInvoice.invoice_type.in_(_FORWARD_INVOICE_TYPES),
            "invoice", "output", negate=False,
        )
        credit_note_rows = await _rows(
            SalesInvoice, SalesInvoice.invoice_date, SalesInvoice.invoice_type == "credit_note",
            "credit_note", "output", negate=True,
        )
        bill_rows = await _rows(
            VendorBill, VendorBill.bill_date, VendorBill.bill_type == "standard",
            "bill", "input", negate=False,
        )
        debit_note_rows = await _rows(
            VendorBill, VendorBill.bill_date, VendorBill.bill_type == "debit_note",
            "debit_note", "input", negate=True,
        )

        lines = invoice_rows + credit_note_rows + bill_rows + debit_note_rows
        lines.sort(key=lambda r: (r["document_date"], r["number"]))
        return lines

    async def get_reconciliation(self, *, company_id: UUID, date_from: date, date_to: date) -> dict:
        """Ties VAT Summary to the GL it's supposed to be a subledger of —
        the same standing-prevention discipline already applied to
        Inventory Valuation and Fixed Assets (both have their own
        `get_reconciliation`). `vat_summary` computes output/input VAT
        independently from source documents (SalesInvoice/VendorBill);
        the GL side reads the real posted journal_entry_line rows for the
        VAT Payable (2200) account over the exact same period, exactly
        like Trial Balance does. The two are computed via entirely
        different paths and can silently drift apart whenever a new
        document type's own VAT treatment isn't mirrored in both places —
        exactly what happened with vendor debit notes (see
        `vat_summary`'s own docstring for the real gap this closed, SAR
        16,822,500 on a real company) — so this exists specifically to
        catch the next one immediately instead of only when someone
        happens to compare the two reports by hand. Never adjusts either
        number to force a match — a real gap is shown as a real gap."""
        assert self.journal_entry_repo is not None
        summary = await self.vat_summary(company_id=company_id, date_from=date_from, date_to=date_to)

        rows = await self.journal_entry_repo.trial_balance(company_id, date_from, date_to, None)
        vat_row = next((r for r in rows if r["account_code"] == ACCOUNT_CODE_VAT_PAYABLE), None)
        gl_net_vat_payable = (
            (vat_row["period_credit"] - vat_row["period_debit"]) if vat_row is not None else Decimal("0")
        )

        difference = summary["net_vat_payable"] - gl_net_vat_payable
        return {
            "date_from": date_from,
            "date_to": date_to,
            "summary_net_vat_payable": summary["net_vat_payable"],
            "gl_net_vat_payable": gl_net_vat_payable,
            "difference": difference,
            "tolerance": VAT_RECONCILIATION_TOLERANCE,
            "matched": abs(difference) <= VAT_RECONCILIATION_TOLERANCE,
        }


# ── Inventory Valuation ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InventoryValuationRow:
    product_id: UUID
    product_code: str
    product_name: str
    warehouse_id: UUID
    warehouse_name: str
    qty_on_hand: Decimal
    unit_cost: Decimal
    total_value: Decimal


@dataclass(frozen=True)
class InventoryReconciliationResult:
    gl_balance: Decimal
    valuation_total: Decimal
    difference: Decimal
    tolerance: Decimal
    matched: bool


# Same subtree-walking convention as every other "the real account might be
# split into children by now" balance lookup in this codebase.
ACCOUNT_CODE_INVENTORY = "1300"
# Small, fixed, and explicit rather than proportional -- large enough to
# absorb genuinely unavoidable sub-cent rounding, never large enough to
# mask a real gap. Never used to force a MATCHED status; only to decide
# which label to show.
INVENTORY_RECONCILIATION_TOLERANCE = Decimal("1.00")


class InventoryValuationReportService:
    """Product Owner audit — "what is my stock worth right now?" is a
    standard report in every reference ERP and was entirely absent here,
    even though the costing engine to answer it correctly already existed
    (`InventoryValuationService` in the inventory module maintains exactly
    the two structures this report reads).

    Correctness detail that matters: `StockQuant.moving_avg_cost` is only
    ever updated for `average`-method companies (see
    `InventoryValuationService.receive_stock`) — for a `fifo` company it
    stays stale/zero, and the true remaining cost basis lives in
    `StockLayer.qty_remaining * unit_cost` instead. Reading the wrong
    structure for a company's actual valuation method would silently
    understate or zero out the report, so this branches on
    `company.valuation_method` exactly like the transactional engine does,
    rather than picking one structure for every company.

    A second correctness detail, found live against a real company's data
    (Trial Balance's Inventory account disagreeing with this report by a
    material amount): `StockQuant.qty_on_hand` for an `average`-method
    company can legitimately go negative — `InventoryService.issue_stock`
    is called with `allow_negative=True` for a Vendor Debit Note return
    (FR-INV-007 override, `purchasing/application/services.py`), and that
    same call posts a real Journal Entry against account 1300 for the
    exact same cost. The GL therefore always reflects 100% of that
    movement. This report previously filtered `qty_on_hand > 0` before
    summing per product+warehouse, which silently dropped every negative
    position from the total instead of netting it in — overstating
    reported inventory value by exactly the value of the excluded
    negative rows, with no corresponding error or warning. The sum must
    include negative rows so this report and Trial Balance always
    reconcile to the same figure, the same way Balance Sheet/Cash Flow/
    Equity Statement are proven to reconcile with each other elsewhere in
    this codebase.
    """

    def __init__(self, session: AsyncSession, journal_entry_repo: JournalEntryRepository | None = None):
        self.session = session
        # Optional so existing call sites/tests building this service
        # without a journal_entry_repo (valuation() never needed one)
        # keep working unchanged -- only get_reconciliation uses it.
        self.journal_entry_repo = journal_entry_repo

    async def valuation(
        self, *, company_id: UUID, valuation_method: str, warehouse_id: UUID | None = None
    ) -> list[InventoryValuationRow]:
        if valuation_method == "fifo":
            query = (
                select(
                    StockLayer.product_id,
                    Location.warehouse_id,
                    func.sum(StockLayer.qty_remaining).label("qty"),
                    func.sum(StockLayer.qty_remaining * StockLayer.unit_cost).label("value"),
                )
                .join(Location, Location.id == StockLayer.location_id)
                .where(StockLayer.company_id == company_id, StockLayer.qty_remaining > 0)
                .group_by(StockLayer.product_id, Location.warehouse_id)
            )
        else:
            query = (
                select(
                    StockQuant.product_id,
                    Location.warehouse_id,
                    func.sum(StockQuant.qty_on_hand).label("qty"),
                    func.sum(StockQuant.qty_on_hand * StockQuant.moving_avg_cost).label("value"),
                )
                .join(Location, Location.id == StockQuant.location_id)
                .where(StockQuant.company_id == company_id)
                .group_by(StockQuant.product_id, Location.warehouse_id)
            )
        if warehouse_id is not None:
            query = query.where(Location.warehouse_id == warehouse_id)

        rows = (await self.session.execute(query)).all()
        if not rows:
            return []

        product_ids = {r.product_id for r in rows}
        warehouse_ids = {r.warehouse_id for r in rows}
        products = {
            p.id: p
            for p in (await self.session.execute(select(Product).where(Product.id.in_(product_ids)))).scalars()
        }
        warehouses = {
            w.id: w
            for w in (await self.session.execute(select(Warehouse).where(Warehouse.id.in_(warehouse_ids)))).scalars()
        }

        result = []
        for r in rows:
            product = products.get(r.product_id)
            warehouse = warehouses.get(r.warehouse_id)
            qty = Decimal(str(r.qty))
            value = Decimal(str(r.value)).quantize(Decimal("0.0001"))
            unit_cost = (value / qty).quantize(Decimal("0.0001")) if qty else Decimal("0")
            result.append(
                InventoryValuationRow(
                    product_id=r.product_id,
                    product_code=product.sku if product else "",
                    product_name=product.name if product else "",
                    warehouse_id=r.warehouse_id,
                    warehouse_name=warehouse.name if warehouse else "",
                    qty_on_hand=qty,
                    unit_cost=unit_cost,
                    total_value=value,
                )
            )
        result.sort(key=lambda row: (row.warehouse_name, row.product_name))
        return result

    async def get_reconciliation(self, *, company_id: UUID, valuation_method: str) -> InventoryReconciliationResult:
        """Ties Inventory Valuation to the GL it's supposed to be a
        subledger of -- the same discipline already applied to Fixed
        Assets (get_reconciliation) and AR/AP. Both totals are computed
        independently: the GL side reads real posted journal_entry_line
        rows for the Inventory (1300) subtree, exactly like Trial Balance
        does; the register side is this service's own `valuation()`,
        unchanged. Never adjusts either number to force a match -- a real
        gap is shown as a real gap, not hidden."""
        assert self.journal_entry_repo is not None
        rows = await self.valuation(company_id=company_id, valuation_method=valuation_method)
        valuation_total = sum((r.total_value for r in rows), Decimal("0"))
        # account_balance_by_root_code filters entry_date <= as_of_date
        # (inclusive already), unlike account_balance_by_id's exclusive
        # cutoff -- no +1 day adjustment needed here.
        gl_balance = await self.journal_entry_repo.account_balance_by_root_code(
            company_id, ACCOUNT_CODE_INVENTORY, date.today()
        )
        difference = valuation_total - gl_balance
        return InventoryReconciliationResult(
            gl_balance=gl_balance,
            valuation_total=valuation_total,
            difference=difference,
            tolerance=INVENTORY_RECONCILIATION_TOLERANCE,
            matched=abs(difference) <= INVENTORY_RECONCILIATION_TOLERANCE,
        )
