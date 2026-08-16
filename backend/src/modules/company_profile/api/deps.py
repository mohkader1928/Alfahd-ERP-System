"""FastAPI dependencies for Company Profile + Sizing Engine (Adaptive ERP Stage 2.1-2.2)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.company_profile.application.services import (
    BlueprintService,
    CompanyProfileService,
    ConfigurationEngineService,
    SizingEngineService,
)
from src.modules.company_profile.infrastructure.repositories import (
    CompanyProfileRepository,
    ConfigurationPlanItemRepository,
    ConfigurationPlanRepository,
    ErpBlueprintRepository,
    SizingResultRepository,
    SizingRuleSetRepository,
)
from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.modules.identity.application.services import CompanyService, UserManagementService
from src.modules.identity.infrastructure.repositories import (
    AuditLogRepository,
    CompanyRepository,
    RoleRepository,
    UserRepository,
)
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


def get_configuration_plan_repo(db: AsyncSession = Depends(get_db)) -> ConfigurationPlanRepository:
    return ConfigurationPlanRepository(db)


def get_configuration_plan_item_repo(db: AsyncSession = Depends(get_db)) -> ConfigurationPlanItemRepository:
    return ConfigurationPlanItemRepository(db)


def get_configuration_engine_service(
    db: AsyncSession = Depends(get_db),
    blueprint_repo: ErpBlueprintRepository = Depends(get_erp_blueprint_repo),
    plan_repo: ConfigurationPlanRepository = Depends(get_configuration_plan_repo),
    item_repo: ConfigurationPlanItemRepository = Depends(get_configuration_plan_item_repo),
) -> ConfigurationEngineService:
    """Constructs identity's CompanyService/UserManagementService directly
    here (company_profile -> identity is an established, one-way module
    dependency, same as AuditLogRepository above) rather than adding a DI
    helper inside identity/api/deps.py -- identity is the single approved
    exception module this stage, and that exception is scoped to
    CompanyService.set_po_approval_threshold only, not to new DI wiring."""
    audit_repo = AuditLogRepository(db)
    company_service = CompanyService(CompanyRepository(db), audit_repo)
    user_management_service = UserManagementService(UserRepository(db), RoleRepository(db), CompanyRepository(db))
    return ConfigurationEngineService(
        db, blueprint_repo, plan_repo, item_repo, company_service, user_management_service, audit_repo
    )
