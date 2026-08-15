"""Repositories for Company Profile + Sizing Engine (Adaptive ERP Stage 2.1-2.2)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.company_profile.infrastructure.models import (
    CompanyProfile,
    SizingResult,
    SizingRuleSet,
)


class CompanyProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, profile: CompanyProfile) -> CompanyProfile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get_by_id(self, profile_id: UUID) -> CompanyProfile | None:
        result = await self.session.execute(select(CompanyProfile).where(CompanyProfile.id == profile_id))
        return result.scalar_one_or_none()

    async def get_by_company(self, company_id: UUID) -> CompanyProfile | None:
        result = await self.session.execute(
            select(CompanyProfile).where(CompanyProfile.company_id == company_id)
        )
        return result.scalar_one_or_none()


class SizingRuleSetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active(self) -> SizingRuleSet | None:
        result = await self.session.execute(
            select(SizingRuleSet).where(SizingRuleSet.is_active.is_(True)).order_by(SizingRuleSet.version.desc())
        )
        return result.scalars().first()

    async def get_by_version(self, version: str) -> SizingRuleSet | None:
        result = await self.session.execute(select(SizingRuleSet).where(SizingRuleSet.version == version))
        return result.scalar_one_or_none()


class SizingResultRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, result: SizingResult) -> SizingResult:
        self.session.add(result)
        await self.session.flush()
        return result

    async def get_latest_for_company(self, company_id: UUID) -> SizingResult | None:
        result = await self.session.execute(
            select(SizingResult)
            .where(SizingResult.company_id == company_id)
            .order_by(SizingResult.created_at.desc())
        )
        return result.scalars().first()

    async def get_by_id(self, result_id: UUID) -> SizingResult | None:
        result = await self.session.execute(select(SizingResult).where(SizingResult.id == result_id))
        return result.scalar_one_or_none()
