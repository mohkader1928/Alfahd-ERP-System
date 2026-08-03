"""FastAPI dependencies for Payments."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import (
    AccountRepository,
    FiscalPeriodRepository,
    JournalEntryRepository,
    JournalRepository,
)
from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.modules.identity.infrastructure.repositories import PartnerRepository
from src.modules.payments.application.services import PaymentService, SubledgerService
from src.modules.payments.infrastructure.repositories import PaymentRepository
from src.modules.purchasing.infrastructure.repositories import VendorBillRepository
from src.modules.sales.infrastructure.repositories import SalesInvoiceRepository
from src.shared.infrastructure.db.session import get_db


def get_payment_repo(db: AsyncSession = Depends(get_db)) -> PaymentRepository:
    return PaymentRepository(db)


def get_partner_repo(db: AsyncSession = Depends(get_db)) -> PartnerRepository:
    return PartnerRepository(db)


def get_subledger_service(
    db: AsyncSession = Depends(get_db), payment_repo: PaymentRepository = Depends(get_payment_repo)
) -> SubledgerService:
    return SubledgerService(
        payment_repo=payment_repo,
        sales_invoice_repo=SalesInvoiceRepository(db),
        vendor_bill_repo=VendorBillRepository(db),
        partner_repo=PartnerRepository(db),
    )


async def get_payment_service(
    db: AsyncSession = Depends(get_db),
    payment_repo: PaymentRepository = Depends(get_payment_repo),
) -> PaymentService:
    journal_entry_service = JournalEntryService(
        JournalEntryRepository(db),
        JournalRepository(db),
        AccountRepository(db),
        FiscalPeriodRepository(db),
    )
    return PaymentService(
        payment_repo=payment_repo,
        sales_invoice_repo=SalesInvoiceRepository(db),
        vendor_bill_repo=VendorBillRepository(db),
        account_repo=AccountRepository(db),
        journal_entry_service=journal_entry_service,
    )
