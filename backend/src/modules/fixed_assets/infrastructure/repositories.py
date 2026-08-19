"""Repository implementations for Fixed Assets (P0-5, 3-Day Brief)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.fixed_assets.infrastructure.models import (
    FixedAsset,
    FixedAssetCategory,
    FixedAssetDepreciationEntry,
)


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

    async def list_by_company(
        self,
        company_id: UUID,
        *,
        active_only: bool = False,
        category_id: UUID | None = None,
        status: str | None = None,
    ) -> list[FixedAsset]:
        query = select(FixedAsset).where(FixedAsset.company_id == company_id)
        if active_only:
            query = query.where(FixedAsset.disposed_at.is_(None))
        if category_id is not None:
            query = query.where(FixedAsset.category_id == category_id)
        if status == "disposed":
            query = query.where(FixedAsset.disposed_at.isnot(None))
        elif status in ("active", "idle", "under_maintenance"):
            # Operational status is only meaningful for a not-yet-disposed
            # asset -- a disposed asset never matches an operational filter,
            # regardless of whatever status it carried at disposal time.
            query = query.where(FixedAsset.disposed_at.is_(None), FixedAsset.status == status)
        result = await self.session.execute(query.order_by(FixedAsset.acquisition_date.desc()))
        return list(result.scalars().all())

    async def count_by_category(self, company_id: UUID, category_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(FixedAsset)
            .where(FixedAsset.company_id == company_id, FixedAsset.category_id == category_id)
        )
        return result.scalar_one()


class FixedAssetCategoryRepository:
    """Mirrors ProductCategoryRepository exactly — see that class
    (identity/infrastructure/repositories.py) for the pattern."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, category: FixedAssetCategory) -> FixedAssetCategory:
        self.session.add(category)
        await self.session.flush()
        return category

    async def get_by_id(self, company_id: UUID, category_id: UUID) -> FixedAssetCategory | None:
        result = await self.session.execute(
            select(FixedAssetCategory).where(
                FixedAssetCategory.id == category_id, FixedAssetCategory.company_id == company_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID) -> list[FixedAssetCategory]:
        result = await self.session.execute(
            select(FixedAssetCategory)
            .where(FixedAssetCategory.company_id == company_id)
            .order_by(FixedAssetCategory.name)
        )
        return list(result.scalars().all())

    async def find_sibling_by_name(
        self, company_id: UUID, parent_id: UUID | None, name: str, *, exclude_id: UUID | None = None
    ) -> FixedAssetCategory | None:
        stmt = select(FixedAssetCategory).where(
            FixedAssetCategory.company_id == company_id,
            func.lower(FixedAssetCategory.name) == name.lower(),
        )
        stmt = (
            stmt.where(FixedAssetCategory.parent_id == parent_id)
            if parent_id is not None
            else stmt.where(FixedAssetCategory.parent_id.is_(None))
        )
        if exclude_id is not None:
            stmt = stmt.where(FixedAssetCategory.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_children(self, company_id: UUID, category_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(FixedAssetCategory)
            .where(FixedAssetCategory.company_id == company_id, FixedAssetCategory.parent_id == category_id)
        )
        return result.scalar_one()

    async def delete(self, category: FixedAssetCategory) -> None:
        await self.session.delete(category)
        await self.session.flush()


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

    async def list_for_company_in_range(
        self, company_id: UUID, date_from: date, date_to: date, *, asset_ids: list[UUID] | None = None
    ) -> list[FixedAssetDepreciationEntry]:
        """Company-wide Depreciation Schedule report — every posted entry
        in the window, across all assets. `asset_ids` (when given) scopes
        this to one category's assets, the same way run_depreciation's
        category filter narrows which assets get a NEW entry posted; this
        narrows which already-posted entries are reported."""
        query = select(FixedAssetDepreciationEntry).where(
            FixedAssetDepreciationEntry.company_id == company_id,
            FixedAssetDepreciationEntry.period_month >= date_from,
            FixedAssetDepreciationEntry.period_month <= date_to,
        )
        if asset_ids is not None:
            query = query.where(FixedAssetDepreciationEntry.fixed_asset_id.in_(asset_ids))
        result = await self.session.execute(
            query.order_by(FixedAssetDepreciationEntry.period_month, FixedAssetDepreciationEntry.fixed_asset_id)
        )
        return list(result.scalars().all())
