"""Repositories for Company Profile + Sizing Engine (Adaptive ERP Stage 2.1-2.2)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.company_profile.infrastructure.models import (
    CompanyProfile,
    ConfigurationPlan,
    ConfigurationPlanItem,
    ErpBlueprint,
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


class ErpBlueprintRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, blueprint: ErpBlueprint) -> ErpBlueprint:
        self.session.add(blueprint)
        await self.session.flush()
        return blueprint

    async def get_by_id(self, blueprint_id: UUID) -> ErpBlueprint | None:
        result = await self.session.execute(select(ErpBlueprint).where(ErpBlueprint.id == blueprint_id))
        return result.scalar_one_or_none()

    async def get_latest_for_company(self, company_id: UUID) -> ErpBlueprint | None:
        result = await self.session.execute(
            select(ErpBlueprint)
            .where(ErpBlueprint.company_id == company_id)
            .order_by(ErpBlueprint.blueprint_version.desc())
        )
        return result.scalars().first()

    async def list_for_company(self, company_id: UUID) -> list[ErpBlueprint]:
        result = await self.session.execute(
            select(ErpBlueprint)
            .where(ErpBlueprint.company_id == company_id)
            .order_by(ErpBlueprint.blueprint_version.desc())
        )
        return list(result.scalars().all())

    async def get_next_version(self, company_id: UUID) -> int:
        latest = await self.get_latest_for_company(company_id)
        return 1 if latest is None else latest.blueprint_version + 1

    async def get_approved_for_company(self, company_id: UUID) -> ErpBlueprint | None:
        """At most one row can ever be status='approved' per company
        (BlueprintService.approve() supersedes the prior one) -- this is
        the single source of truth Configuration Plan creation reads."""
        result = await self.session.execute(
            select(ErpBlueprint).where(ErpBlueprint.company_id == company_id, ErpBlueprint.status == "approved")
        )
        return result.scalar_one_or_none()


class ConfigurationPlanRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, plan: ConfigurationPlan) -> ConfigurationPlan:
        self.session.add(plan)
        await self.session.flush()
        return plan

    async def get_by_id(self, plan_id: UUID) -> ConfigurationPlan | None:
        result = await self.session.execute(select(ConfigurationPlan).where(ConfigurationPlan.id == plan_id))
        return result.scalar_one_or_none()

    async def get_by_company_and_blueprint(self, company_id: UUID, blueprint_id: UUID) -> ConfigurationPlan | None:
        result = await self.session.execute(
            select(ConfigurationPlan).where(
                ConfigurationPlan.company_id == company_id, ConfigurationPlan.blueprint_id == blueprint_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_company(self, company_id: UUID) -> list[ConfigurationPlan]:
        result = await self.session.execute(
            select(ConfigurationPlan)
            .where(ConfigurationPlan.company_id == company_id)
            .order_by(ConfigurationPlan.created_at.desc())
        )
        return list(result.scalars().all())


class ConfigurationPlanItemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, item: ConfigurationPlanItem) -> ConfigurationPlanItem:
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_for_plan(self, plan_id: UUID) -> list[ConfigurationPlanItem]:
        result = await self.session.execute(
            select(ConfigurationPlanItem)
            .where(ConfigurationPlanItem.plan_id == plan_id)
            .order_by(ConfigurationPlanItem.decision_key)
        )
        return list(result.scalars().all())
