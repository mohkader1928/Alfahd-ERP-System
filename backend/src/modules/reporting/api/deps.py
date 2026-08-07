"""FastAPI dependencies for Reporting."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.infrastructure.repositories import JournalEntryRepository
from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.modules.payments.infrastructure.repositories import PaymentRepository
from src.modules.purchasing.infrastructure.repositories import (
    PurchaseOrderRepository,
    VendorBillRepository,
)
from src.modules.reporting.application.services import (
    DashboardService,
    SalesReportingService,
    SearchService,
    VatReportingService,
)
from src.modules.sales.infrastructure.repositories import SalesInvoiceRepository
from src.shared.infrastructure.db.session import get_db


def get_dashboard_service(db: AsyncSession = Depends(get_db)) -> DashboardService:
    return DashboardService(
        SalesInvoiceRepository(db),
        VendorBillRepository(db),
        JournalEntryRepository(db),
        order_repo=PurchaseOrderRepository(db),
        payment_repo=PaymentRepository(db),
    )


def get_sales_reporting_service(db: AsyncSession = Depends(get_db)) -> SalesReportingService:
    return SalesReportingService(db)


def get_search_service(db: AsyncSession = Depends(get_db)) -> SearchService:
    return SearchService(db)


def get_vat_reporting_service(db: AsyncSession = Depends(get_db)) -> VatReportingService:
    return VatReportingService(db)
