"""FastAPI dependencies for Company Profile + Sizing Engine (Adaptive ERP Stage 2.1-2.2)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.company_profile.application.services import (
    BlueprintService,
    CompanyProfileService,
    SizingEngineService,
)
from src.modules.company_profile.infrastructure.repositories import (
    CompanyProfileRepository,
    ErpBlueprintRepository,
    SizingResultRepository,
    SizingRuleSetRepository,
)
from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.modules.identity.infrastructure.repositories import AuditLogRepository
from src.shared.infrastructure.db.session import get_db


def get_company_profile_repo(db: AsyncSession = Depends(get_db)) -> CompanyProfileRepository:
    return CompanyProfileRepository(db)


def get_company_profile_service(
    db: AsyncSession = Depends(get_db),
    profile_repo: CompanyProfileRepository = Depends(get_company_profile_repo),
) -> CompanyProfileService:
    return CompanyProfileService(profile_repo, AuditLogRepository(db))


def get_sizing_rule_set_repo(db: AsyncSession = Depends(get_db)) -> SizingRuleSetRepository:
    return SizingRuleSetRepository(db)


def get_sizing_result_repo(db: AsyncSession = Depends(get_db)) -> SizingResultRepository:
    return SizingResultRepository(db)


def get_sizing_engine_service(
    profile_repo: CompanyProfileRepository = Depends(get_company_profile_repo),
    rule_set_repo: SizingRuleSetRepository = Depends(get_sizing_rule_set_repo),
    result_repo: SizingResultRepository = Depends(get_sizing_result_repo),
) -> SizingEngineService:
    return SizingEngineService(profile_repo, rule_set_repo, result_repo)


def get_erp_blueprint_repo(db: AsyncSession = Depends(get_db)) -> ErpBlueprintRepository:
    return ErpBlueprintRepository(db)


def get_blueprint_service(
    profile_repo: CompanyProfileRepository = Depends(get_company_profile_repo),
    rule_set_repo: SizingRuleSetRepository = Depends(get_sizing_rule_set_repo),
    result_repo: SizingResultRepository = Depends(get_sizing_result_repo),
    blueprint_repo: ErpBlueprintRepository = Depends(get_erp_blueprint_repo),
) -> BlueprintService:
    return BlueprintService(profile_repo, rule_set_repo, result_repo, blueprint_repo)
