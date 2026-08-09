"""Repository implementations for Fixed Assets (P0-5, 3-Day Brief)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.fixed_assets.infrastructure.models import FixedAsset, FixedAssetDepreciationEntry


class FixedAssetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, asset: FixedAsset) -> FixedAsset:
        self.session.add(asset)
        await self.session.flush()
        return asset

    async def get_by_id(self, asset_id: UUID) -> FixedAsset | None:
        result = await self.session.execute(select(FixedAsset).where(FixedAsset.id == asset_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, asset_id: UUID) -> FixedAsset | None:
        """Row-locked read for run_depreciation/dispose — two concurrent
        requests against the same asset must not both compute the same
        stale accumulated-depreciation total before either commits."""
        result = await self.session.execute(select(FixedAsset).where(FixedAsset.id == asset_id).with_for_update())
        return result.scalar_one_or_none()

    async def next_number(self, company_id: UUID) -> str:
        result = await self.session.execute(select(func.count()).where(FixedAsset.company_id == company_id))
        count = result.scalar_one()
        return f"FA-{count + 1:06d}"

    async def list_by_company(self, company_id: UUID, *, active_only: bool = False) -> list[FixedAsset]:
        query = select(FixedAsset).where(FixedAsset.company_id == company_id)
        if active_only:
            query = query.where(FixedAsset.disposed_at.is_(None))
        result = await self.session.execute(query.order_by(FixedAsset.acquisition_date.desc()))
        return list(result.scalars().all())


class FixedAssetDepreciationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, entry: FixedAssetDepreciationEntry) -> FixedAssetDepreciationEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def sum_for_asset(self, asset_id: UUID) -> Decimal:
        # coalesce(..., Decimal) rather than a bare 0: with no rows, an
        # integer fallback loses the Numeric(18,4) scale (comes back "0"
        # instead of "0.0000"), a real inconsistency in what the API
        # returns depending on whether the asset has any posted entries.
        result = await self.session.execute(
            select(func.coalesce(func.sum(FixedAssetDepreciationEntry.amount), Decimal("0.0000"))).where(
                FixedAssetDepreciationEntry.fixed_asset_id == asset_id
            )
        )
        return result.scalar_one()

    async def get_for_asset_and_period(
        self, asset_id: UUID, period_month: date
    ) -> FixedAssetDepreciationEntry | None:
        result = await self.session.execute(
            select(FixedAssetDepreciationEntry).where(
                FixedAssetDepreciationEntry.fixed_asset_id == asset_id,
                FixedAssetDepreciationEntry.period_month == period_month,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_asset(self, asset_id: UUID) -> list[FixedAssetDepreciationEntry]:
        result = await self.session.execute(
            select(FixedAssetDepreciationEntry)
            .where(FixedAssetDepreciationEntry.fixed_asset_id == asset_id)
            .order_by(FixedAssetDepreciationEntry.period_month)
        )
        return list(result.scalars().all())
