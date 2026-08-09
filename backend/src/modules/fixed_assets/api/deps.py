"""FastAPI dependencies for Fixed Assets."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import (
    AccountRepository,
    FiscalPeriodRepository,
    JournalEntryRepository,
    JournalRepository,
)
from src.modules.fixed_assets.application.services import FixedAssetService
from src.modules.fixed_assets.infrastructure.repositories import (
    FixedAssetDepreciationRepository,
    FixedAssetRepository,
)
from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.shared.infrastructure.db.session import get_db


def get_fixed_asset_repo(db: AsyncSession = Depends(get_db)) -> FixedAssetRepository:
    return FixedAssetRepository(db)


def get_fixed_asset_depreciation_repo(db: AsyncSession = Depends(get_db)) -> FixedAssetDepreciationRepository:
    return FixedAssetDepreciationRepository(db)


async def get_fixed_asset_service(
    db: AsyncSession = Depends(get_db),
    asset_repo: FixedAssetRepository = Depends(get_fixed_asset_repo),
    depreciation_repo: FixedAssetDepreciationRepository = Depends(get_fixed_asset_depreciation_repo),
) -> FixedAssetService:
    journal_entry_service = JournalEntryService(
        JournalEntryRepository(db), JournalRepository(db), AccountRepository(db), FiscalPeriodRepository(db)
    )
    return FixedAssetService(
        asset_repo=asset_repo,
        depreciation_repo=depreciation_repo,
        account_repo=AccountRepository(db),
        journal_entry_service=journal_entry_service,
    )
