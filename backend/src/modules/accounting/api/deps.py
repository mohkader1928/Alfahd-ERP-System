"""FastAPI dependencies for Accounting. RBAC reuses Identity's
`require_permission` directly — every module depends on Identity for
authorization, per Phase 8 §3.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.infrastructure.repositories import (
    AccountRepository,
    AccountTypeRepository,
    FiscalPeriodRepository,
    JournalEntryRepository,
    JournalRepository,
    TaxRepository,
)
from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.shared.infrastructure.db.session import get_db


def get_account_repo(db: AsyncSession = Depends(get_db)) -> AccountRepository:
    return AccountRepository(db)


def get_account_type_repo(db: AsyncSession = Depends(get_db)) -> AccountTypeRepository:
    return AccountTypeRepository(db)


def get_journal_repo(db: AsyncSession = Depends(get_db)) -> JournalRepository:
    return JournalRepository(db)


def get_tax_repo(db: AsyncSession = Depends(get_db)) -> TaxRepository:
    return TaxRepository(db)


def get_fiscal_period_repo(db: AsyncSession = Depends(get_db)) -> FiscalPeriodRepository:
    return FiscalPeriodRepository(db)


def get_journal_entry_repo(db: AsyncSession = Depends(get_db)) -> JournalEntryRepository:
    return JournalEntryRepository(db)
