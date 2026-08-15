"""Repository for Company Profile (Adaptive ERP Stage 2.1)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.company_profile.infrastructure.models import CompanyProfile


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
