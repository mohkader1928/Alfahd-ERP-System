"""FastAPI routes for Reporting, per Phase 10 §6.6."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.api.deps import get_company_repo
from src.modules.identity.infrastructure.repositories import AuditLogRepository, CompanyRepository
from src.modules.reporting.api.deps import (
    get_dashboard_service,
    get_inventory_valuation_service,
    get_purchase_reporting_service,
    get_sales_reporting_service,
    get_search_service,
    get_vat_reporting_service,
    require_permission,
)
from src.modules.reporting.api.schemas import (
    DashboardSummaryOut,
    InventoryReconciliationOut,
    InventoryValuationRowOut,
    PurchaseByVendorRow,
    SalesByCustomerRow,
    SalesByPeriodRow,
    SalesByProductRow,
    SearchResultRow,
    VatSummaryOut,
)
from src.modules.reporting.application.services import (
    DashboardService,
    InventoryValuationReportService,
    PurchaseReportingService,
    SalesReportingService,
    SearchService,
    VatReportingService,
)
from src.modules.reporting.infrastructure.csv_exporter import rows_to_csv
from src.modules.sales.infrastructure.repositories import SalesInvoiceRepository
from src.shared.infrastructure.db.session import get_db
from src.shared.reporting.company_name import resolve_company_name
from src.shared.reporting.export_render import ReportColumn, ReportTable
from src.shared.reporting.export_response import build_export_response
from src.shared.reporting.formatting import format_amount, format_qty
from src.shared.reporting.labels import label, title
from src.shared.security.auth_context import AuthContext

router = APIRouter()

ExportFormatParam = Literal["json", "pdf", "xlsx"]


@router.get("/dashboard", response_model=DashboardSummaryOut)
async def get_dashboard(
    period_start: date,
    period_end: date,
    ctx: AuthContext = Depends(require_permission("reporting.dashboard.view")),
    service: DashboardService = Depends(get_dashboard_service),
):
    return await service.get_summary(company_id=ctx.company_id, period_start=period_start, period_end=period_end)


@router.get("/search", response_model=list[SearchResultRow])
async def search(
    q: str,
    ctx: AuthContext = Depends(require_permission("search.use")),
    service: SearchService = Depends(get_search_service),
):
    """Professional Workspace Layer — Global Search across partners,
    products, sales quotations/orders/invoices, purchase orders, and
    vendor bills. See SearchService's docstring for the permission model."""
    if len(q.strip()) < 2:
        return []
    return await service.search(company_id=ctx.company_id, query=q.strip())


@router.get("/export/sales-invoices")
async def export_sales_invoices(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("reporting.export")),
):
    """FR-RPT-001/002: CSV export (opens natively in Excel)."""
    invoices = await SalesInvoiceRepository(db).list_by_company(ctx.company_id)
    csv_body = rows_to_csv(
        fieldnames=["number", "invoice_type", "status", "invoice_date", "subtotal_amount", "tax_amount", "total_amount"],
        rows=[
            {
                "number": inv.number,
                "invoice_type": inv.invoice_type,
                "status": inv.status,
                "invoice_date": inv.invoice_date.isoformat(),
                "subtotal_amount": str(inv.subtotal_amount),
                "tax_amount": str(inv.tax_amount),
                "total_amount": str(inv.total_amount),
            }
            for inv in invoices
        ],
    )
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_invoices.csv"},
    )


@router.get("/export/audit-log")
async def export_audit_log(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("reporting.export")),
):
    """FR-RPT-004: audit trail export for compliance purposes."""
    entries = await AuditLogRepository(db).list_by_company(ctx.company_id, limit=500)
    csv_body = rows_to_csv(
        fieldnames=["changed_at", "user_id", "target_table", "target_id", "field_name", "old_value", "new_value"],
        rows=[
            {
                "changed_at": entry.changed_at.isoformat(),
                "user_id": str(entry.user_id) if entry.user_id else "",
                "target_table": entry.target_table,
                "target_id": str(entry.target_id),
                "field_name": entry.field_name,
                "old_value": entry.old_value or "",
                "new_value": entry.new_value or "",
            }
            for entry in entries
        ],
    )
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


# ── Sales Reports ──────────────────────────────────────────────────────────────

def _sales_totals(rows: list[dict]) -> tuple:
    subtotal = sum((r["subtotal"] for r in rows), start=Decimal("0"))
    tax = sum((r["tax_amount"] for r in rows), start=Decimal("0"))
    total = sum((r["total"] for r in rows), start=Decimal("0"))
    return subtotal, tax, total


@router.get("/sales/by-customer", response_model=list[SalesByCustomerRow])
async def sales_by_customer(
    date_from: date,
    date_to: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("reporting.sales.view")),
    service: SalesReportingService = Depends(get_sales_reporting_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """FR-RPT: Sales revenue grouped by customer for a date range."""
    rows = await service.by_customer(company_id=ctx.company_id, date_from=date_from, date_to=date_to)
    if format == "json":
        return rows
    subtotal, tax, total = _sales_totals(rows)
    total_payments = sum((r["payments_received"] for r in rows), Decimal("0"))
    total_balance = sum((r["balance"] for r in rows), Decimal("0"))
    table = ReportTable(
        title=title(lang, "sales_by_customer"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f"{date_from} — {date_to}",
        columns=[
            ReportColumn(label(lang, "customer")),
            ReportColumn(label(lang, "invoice_count"), "end"),
            ReportColumn(label(lang, "amount"), "end"),
            ReportColumn("VAT", "end"),
            ReportColumn(label(lang, "total"), "end"),
            ReportColumn(label(lang, "payments_received"), "end"),
            ReportColumn(label(lang, "balance"), "end"),
        ],
        rows=[
            [
                r["partner_name"],
                str(r["invoice_count"]),
                format_amount(r["subtotal"]),
                format_amount(r["tax_amount"]),
                format_amount(r["total"]),
                format_amount(r["payments_received"]),
                format_amount(r["balance"]),
            ]
            for r in rows
        ],
        totals=[
            label(lang, "total"),
            "",
            format_amount(subtotal),
            format_amount(tax),
            format_amount(total),
            format_amount(total_payments),
            format_amount(total_balance),
        ],
        rtl=lang == "ar",
    )
    return build_export_response(format, "sales-by-customer", table)


@router.get("/sales/by-product", response_model=list[SalesByProductRow])
async def sales_by_product(
    date_from: date,
    date_to: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("reporting.sales.view")),
    service: SalesReportingService = Depends(get_sales_reporting_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """FR-RPT: Sales revenue grouped by product (via invoice lines) for a date range."""
    rows = await service.by_product(company_id=ctx.company_id, date_from=date_from, date_to=date_to)
    if format == "json":
        return rows
    subtotal, tax, total = _sales_totals(rows)
    table = ReportTable(
        title=title(lang, "sales_by_product"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f"{date_from} — {date_to}",
        columns=[
            ReportColumn(label(lang, "product")),
            ReportColumn(label(lang, "qty"), "end"),
            ReportColumn(label(lang, "amount"), "end"),
            ReportColumn("VAT", "end"),
            ReportColumn(label(lang, "total"), "end"),
        ],
        rows=[
            [f"{r['product_code']} — {r['product_name']}", format_qty(r["qty_sold"]), format_amount(r["subtotal"]), format_amount(r["tax_amount"]), format_amount(r["total"])]
            for r in rows
        ],
        totals=[label(lang, "total"), "", format_amount(subtotal), format_amount(tax), format_amount(total)],
        rtl=lang == "ar",
    )
    return build_export_response(format, "sales-by-product", table)


@router.get("/sales/by-period", response_model=list[SalesByPeriodRow])
async def sales_by_period(
    date_from: date,
    date_to: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("reporting.sales.view")),
    service: SalesReportingService = Depends(get_sales_reporting_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """FR-RPT: Sales revenue grouped by calendar month for a date range."""
    rows = await service.by_period(company_id=ctx.company_id, date_from=date_from, date_to=date_to)
    if format == "json":
        return rows
    subtotal, tax, total = _sales_totals(rows)
    table = ReportTable(
        title=title(lang, "sales_by_period"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f"{date_from} — {date_to}",
        columns=[
            ReportColumn(label(lang, "period")),
            ReportColumn(label(lang, "invoice_count"), "end"),
            ReportColumn(label(lang, "amount"), "end"),
            ReportColumn("VAT", "end"),
            ReportColumn(label(lang, "total"), "end"),
        ],
        rows=[
            [r["period_label"], str(r["invoice_count"]), format_amount(r["subtotal"]), format_amount(r["tax_amount"]), format_amount(r["total"])]
            for r in rows
        ],
        totals=[label(lang, "total"), "", format_amount(subtotal), format_amount(tax), format_amount(total)],
        rtl=lang == "ar",
    )
    return build_export_response(format, "sales-by-period", table)


# ── Purchasing Reports ───────────────────────────────────────────────────────────

def _purchase_totals(rows: list[dict]) -> tuple:
    subtotal = sum((r["subtotal"] for r in rows), start=Decimal("0"))
    tax = sum((r["tax_amount"] for r in rows), start=Decimal("0"))
    total = sum((r["total"] for r in rows), start=Decimal("0"))
    return subtotal, tax, total


@router.get("/purchasing/by-supplier", response_model=list[PurchaseByVendorRow])
async def purchases_by_supplier(
    date_from: date,
    date_to: date,
    partner_id: UUID | None = None,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("reporting.purchasing.view")),
    service: PurchaseReportingService = Depends(get_purchase_reporting_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """P0-3 (3-Day Brief): Purchases grouped by vendor for a date range,
    mirroring /sales/by-customer -- amount/VAT/total, debit-note
    adjustments issued in the period, net purchases after those
    adjustments, payments made, and the vendor's running AP balance as of
    date_to (matches Trial Balance's Accounts Payable, same as
    /sales/by-customer's balance column matches Accounts Receivable)."""
    rows = await service.by_vendor(
        company_id=ctx.company_id, date_from=date_from, date_to=date_to, partner_id=partner_id
    )
    if format == "json":
        return rows
    subtotal, tax, total = _purchase_totals(rows)
    total_adjustments = sum((r["adjustments"] for r in rows), Decimal("0"))
    total_net = sum((r["net_total"] for r in rows), Decimal("0"))
    total_payments = sum((r["payments_made"] for r in rows), Decimal("0"))
    total_balance = sum((r["balance"] for r in rows), Decimal("0"))
    table = ReportTable(
        title=title(lang, "purchases_by_supplier"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f"{date_from} — {date_to}",
        columns=[
            ReportColumn(label(lang, "vendor")),
            ReportColumn(label(lang, "invoice_count"), "end"),
            ReportColumn(label(lang, "amount"), "end"),
            ReportColumn("VAT", "end"),
            ReportColumn(label(lang, "total"), "end"),
            ReportColumn(label(lang, "adjustments"), "end"),
            ReportColumn(label(lang, "net_purchases"), "end"),
            ReportColumn(label(lang, "payments_made"), "end"),
            ReportColumn(label(lang, "balance"), "end"),
        ],
        rows=[
            [
                r["partner_name"],
                str(r["bill_count"]),
                format_amount(r["subtotal"]),
                format_amount(r["tax_amount"]),
                format_amount(r["total"]),
                format_amount(r["adjustments"]),
                format_amount(r["net_total"]),
                format_amount(r["payments_made"]),
                format_amount(r["balance"]),
            ]
            for r in rows
        ],
        totals=[
            label(lang, "total"),
            "",
            format_amount(subtotal),
            format_amount(tax),
            format_amount(total),
            format_amount(total_adjustments),
            format_amount(total_net),
            format_amount(total_payments),
            format_amount(total_balance),
        ],
        rtl=lang == "ar",
    )
    return build_export_response(format, "purchases-by-supplier", table)


# ── VAT / Tax Summary ────────────────────────────────────────────────────────────

@router.get("/vat-summary", response_model=VatSummaryOut)
async def vat_summary(
    date_from: date,
    date_to: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("reporting.vat.view")),
    service: VatReportingService = Depends(get_vat_reporting_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """Owner-requested — the standard baseline every Saudi business needs
    before filing a ZATCA VAT return: output VAT (sales) vs. input VAT
    (purchases) for a period, netted to what's owed or refundable. Only
    counts documents that actually posted to the books."""
    result = await service.vat_summary(company_id=ctx.company_id, date_from=date_from, date_to=date_to)
    if format == "json":
        return VatSummaryOut(date_from=date_from, date_to=date_to, **result)

    table = ReportTable(
        title=title(lang, "vat_summary"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f"{date_from} — {date_to}",
        columns=[ReportColumn(label(lang, "description")), ReportColumn(label(lang, "amount"), "end")],
        rows=[
            [label(lang, "sales_subtotal"), format_amount(result["sales_subtotal"])],
            [label(lang, "output_vat"), format_amount(result["output_vat"])],
            [label(lang, "sales_total"), format_amount(result["sales_total"])],
            [label(lang, "purchases_subtotal"), format_amount(result["purchases_subtotal"])],
            [label(lang, "input_vat"), format_amount(result["input_vat"])],
            [label(lang, "purchases_total"), format_amount(result["purchases_total"])],
        ],
        totals=[label(lang, "net_vat_payable"), format_amount(result["net_vat_payable"])],
        rtl=lang == "ar",
    )
    return build_export_response(format, "vat-summary", table)


# ── Inventory Valuation ────────────────────────────────────────────────────────

@router.get("/inventory-valuation", response_model=list[InventoryValuationRowOut])
async def inventory_valuation(
    warehouse_id: UUID | None = None,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("reporting.inventory_valuation.view")),
    service: InventoryValuationReportService = Depends(get_inventory_valuation_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """Product Owner audit — "what is my stock worth right now?": current
    on-hand quantity and value per product/warehouse, using whichever
    costing method (FIFO or moving average) this company actually runs."""
    company = await company_repo.get_by_id(ctx.company_id)
    valuation_method = company.valuation_method if company else "average"
    rows = await service.valuation(
        company_id=ctx.company_id, valuation_method=valuation_method, warehouse_id=warehouse_id
    )
    if format == "json":
        return rows

    total_value = sum((r.total_value for r in rows), Decimal("0"))
    table = ReportTable(
        title=title(lang, "inventory_valuation"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=None,
        columns=[
            ReportColumn(label(lang, "warehouse")),
            ReportColumn(label(lang, "product")),
            ReportColumn(label(lang, "qty"), "end"),
            ReportColumn(label(lang, "unit_cost"), "end"),
            ReportColumn(label(lang, "total"), "end"),
        ],
        rows=[
            [
                r.warehouse_name,
                f"{r.product_code} — {r.product_name}",
                format_qty(r.qty_on_hand),
                format_amount(r.unit_cost),
                format_amount(r.total_value),
            ]
            for r in rows
        ],
        totals=[label(lang, "total"), "", "", "", format_amount(total_value)],
        rtl=lang == "ar",
    )
    return build_export_response(format, "inventory-valuation", table)


@router.get("/inventory-reconciliation", response_model=InventoryReconciliationOut)
async def inventory_reconciliation(
    ctx: AuthContext = Depends(require_permission("reporting.inventory_valuation.view")),
    service: InventoryValuationReportService = Depends(get_inventory_valuation_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """Owner-reported finding (شركة المحمود, 2026-08-19): Inventory
    Valuation and the Trial Balance's Inventory (1300) balance had
    silently drifted apart. This surfaces that comparison directly,
    every time, instead of relying on someone noticing two separate
    screens disagree -- the same MATCHED/NOT MATCHED discipline Fixed
    Assets' reconciliation report already established."""
    company = await company_repo.get_by_id(ctx.company_id)
    valuation_method = company.valuation_method if company else "average"
    return await service.get_reconciliation(company_id=ctx.company_id, valuation_method=valuation_method)
