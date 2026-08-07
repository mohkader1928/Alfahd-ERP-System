"""FastAPI routes for Reporting, per Phase 10 §6.6."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.api.deps import get_company_repo
from src.modules.identity.infrastructure.repositories import AuditLogRepository, CompanyRepository
from src.modules.reporting.api.deps import (
    get_dashboard_service,
    get_sales_reporting_service,
    require_permission,
)
from src.modules.reporting.api.schemas import (
    DashboardSummaryOut,
    SalesByCustomerRow,
    SalesByPeriodRow,
    SalesByProductRow,
)
from src.modules.reporting.application.services import DashboardService, SalesReportingService
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
        ],
        rows=[
            [r["partner_name"], str(r["invoice_count"]), format_amount(r["subtotal"]), format_amount(r["tax_amount"]), format_amount(r["total"])]
            for r in rows
        ],
        totals=[label(lang, "total"), "", format_amount(subtotal), format_amount(tax), format_amount(total)],
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
