"""FastAPI routes for Reporting, per Phase 10 §6.6."""

from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.infrastructure.repositories import AuditLogRepository
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
from src.shared.security.auth_context import AuthContext

router = APIRouter()


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

@router.get("/sales/by-customer", response_model=list[SalesByCustomerRow])
async def sales_by_customer(
    date_from: date,
    date_to: date,
    ctx: AuthContext = Depends(require_permission("reporting.sales.view")),
    service: SalesReportingService = Depends(get_sales_reporting_service),
):
    """FR-RPT: Sales revenue grouped by customer for a date range."""
    return await service.by_customer(
        company_id=ctx.company_id, date_from=date_from, date_to=date_to
    )


@router.get("/sales/by-product", response_model=list[SalesByProductRow])
async def sales_by_product(
    date_from: date,
    date_to: date,
    ctx: AuthContext = Depends(require_permission("reporting.sales.view")),
    service: SalesReportingService = Depends(get_sales_reporting_service),
):
    """FR-RPT: Sales revenue grouped by product (via invoice lines) for a date range."""
    return await service.by_product(
        company_id=ctx.company_id, date_from=date_from, date_to=date_to
    )


@router.get("/sales/by-period", response_model=list[SalesByPeriodRow])
async def sales_by_period(
    date_from: date,
    date_to: date,
    ctx: AuthContext = Depends(require_permission("reporting.sales.view")),
    service: SalesReportingService = Depends(get_sales_reporting_service),
):
    """FR-RPT: Sales revenue grouped by calendar month for a date range."""
    return await service.by_period(
        company_id=ctx.company_id, date_from=date_from, date_to=date_to
    )
