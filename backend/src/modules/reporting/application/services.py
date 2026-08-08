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

from src.modules.accounting.infrastructure.repositories import JournalEntryRepository
from src.modules.identity.infrastructure.master_data_models import Partner, Product
from src.modules.inventory.infrastructure.models import Location, StockLayer, StockQuant, Warehouse
from src.modules.payments.infrastructure.models import Payment
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
    sales_trend: list[SalesTrendPoint]
    pending_approvals_count: int
    recent_activity: list[RecentActivityItem]


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


def _last_n_months(anchor: date, n: int) -> list[tuple[int, int]]:
    """[(year, month), ...] for the n calendar months ending at `anchor`'s
    month, oldest first — plain integer arithmetic, no calendar library
    needed since we only ever need month/year rollover."""
    months = []
    y, m = anchor.year, anchor.month
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


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
    ):
        self.invoice_repo = invoice_repo
        self.bill_repo = bill_repo
        self.journal_entry_repo = journal_entry_repo
        self.order_repo = order_repo
        self.payment_repo = payment_repo

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
            sales_trend=await self._sales_trend(company_id),
            pending_approvals_count=await self._pending_approvals_count(company_id),
            recent_activity=await self._recent_activity(company_id),
        )

    async def _sales_trend(self, company_id: UUID, *, months: int = 6) -> list[SalesTrendPoint]:
        today = date.today()
        points = []
        for year, month in _last_n_months(today, months):
            start, end = _month_bounds(year, month)
            total = await self.invoice_repo.sum_total_in_range(company_id, start, end)
            points.append(SalesTrendPoint(period_label=f"{year:04d}-{month:02d}", total=total))
        return points

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


class VatReportingService:
    """VAT/Tax Summary — explicitly named in the Owner's original Bundle E
    spec, and the standard baseline every Saudi business needs before
    filing a ZATCA VAT return: output VAT collected on sales vs. input VAT
    paid on purchases for a period, netted to what's actually owed (or
    refundable). Only counts documents that have actually posted to the
    books (`journal_entry_id is not None`) — the same "real accounting
    impact, not just a draft" filter AR/AP Aging already applies."""

    def __init__(self, session: AsyncSession):
        self.session = session

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
        purchases_stmt = select(
            func.coalesce(func.sum(VendorBill.subtotal_amount), 0).label("subtotal"),
            func.coalesce(func.sum(VendorBill.tax_amount), 0).label("vat"),
            func.coalesce(func.sum(VendorBill.total_amount), 0).label("total"),
        ).where(
            VendorBill.company_id == company_id,
            VendorBill.journal_entry_id.is_not(None),
            VendorBill.bill_date >= date_from,
            VendorBill.bill_date <= date_to,
        )

        sales_row = (await self.session.execute(sales_stmt)).one()
        credit_row = (await self.session.execute(credit_note_stmt)).one()
        purchases_row = (await self.session.execute(purchases_stmt)).one()

        sales_subtotal = Decimal(str(sales_row.subtotal)) - Decimal(str(credit_row.subtotal))
        output_vat = Decimal(str(sales_row.vat)) - Decimal(str(credit_row.vat))
        sales_total = Decimal(str(sales_row.total)) - Decimal(str(credit_row.total))
        purchases_subtotal = Decimal(str(purchases_row.subtotal))
        input_vat = Decimal(str(purchases_row.vat))
        purchases_total = Decimal(str(purchases_row.total))

        return {
            "sales_subtotal": sales_subtotal,
            "output_vat": output_vat,
            "sales_total": sales_total,
            "purchases_subtotal": purchases_subtotal,
            "input_vat": input_vat,
            "purchases_total": purchases_total,
            "net_vat_payable": output_vat - input_vat,
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
    """

    def __init__(self, session: AsyncSession):
        self.session = session

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
                .where(StockQuant.company_id == company_id, StockQuant.qty_on_hand > 0)
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
