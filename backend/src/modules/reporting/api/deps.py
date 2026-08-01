"""FastAPI dependencies for Reporting."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.infrastructure.repositories import JournalEntryRepository
from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.modules.purchasing.infrastructure.repositories import VendorBillRepository
from src.modules.reporting.application.services import DashboardService
from src.modules.sales.infrastructure.repositories import SalesInvoiceRepository
from src.shared.infrastructure.db.session import get_db


def get_dashboard_service(db: AsyncSession = Depends(get_db)) -> DashboardService:
    return DashboardService(
        SalesInvoiceRepository(db), VendorBillRepository(db), JournalEntryRepository(db)
    )
