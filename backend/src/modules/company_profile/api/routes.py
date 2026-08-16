"""FastAPI routes for Company Profile (Adaptive ERP Stage 2.1).

See docs/adaptive/03-customer-profile-spec.md for the field-by-field
justification and docs/adaptive/06-configuration-engine-architecture.md
§6.6 for the security posture (same RLS + require_permission mechanism as
every other module — no new isolation or auth mechanism introduced here).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.company_profile.api.deps import (
    get_blueprint_service,
    get_company_profile_repo,
    get_company_profile_service,
    get_configuration_engine_service,
    get_sizing_engine_service,
    require_permission,
)
from src.modules.company_profile.api.schemas import (
    CompanyProfileOut,
    CompanyProfileWriteRequest,
    ConfigurationPlanItemOut,
    ConfigurationPlanOut,
    ErpBlueprintOut,
    SizingResultOut,
)
from src.modules.company_profile.application.services import (
    BlueprintService,
    CompanyProfileService,
    ConfigurationEngineService,
    SizingEngineService,
)
from src.modules.company_profile.infrastructure.models import (
    ConfigurationPlan,
    ConfigurationPlanItem,
)
from src.modules.company_profile.infrastructure.repositories import CompanyProfileRepository
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext

router = APIRouter()


def _plan_out(plan: ConfigurationPlan, items: list[ConfigurationPlanItem]) -> ConfigurationPlanOut:
    return ConfigurationPlanOut(
        id=plan.id,
        company_id=plan.company_id,
        blueprint_id=plan.blueprint_id,
        status=plan.status,
        validated_at=plan.validated_at,
        applied_at=plan.applied_at,
        failure_reason=plan.failure_reason,
        created_at=plan.created_at,
        items=[ConfigurationPlanItemOut.model_validate(i) for i in items],
    )


@router.get("", response_model=CompanyProfileOut)
async def get_company_profile(
    ctx: AuthContext = Depends(require_permission("company_profile.view")),
    profile_repo: CompanyProfileRepository = Depends(get_company_profile_repo),
):
    profile = await profile_repo.get_by_company(ctx.company_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No company profile exists for this company yet")
    return profile


@router.post("", response_model=CompanyProfileOut, status_code=status.HTTP_201_CREATED)
async def create_company_profile(
    payload: CompanyProfileWriteRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("company_profile.manage")),
    service: CompanyProfileService = Depends(get_company_profile_service),
):
    try:
        profile = await service.create(
            tenant_id=ctx.tenant_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            values=payload.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return profile


@router.patch("", response_model=CompanyProfileOut)
async def update_company_profile(
    payload: CompanyProfileWriteRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("company_profile.manage")),
    service: CompanyProfileService = Depends(get_company_profile_service),
):
    try:
        profile = await service.update(
            company_id=ctx.company_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            values=payload.model_dump(exclude_unset=True),
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return profile


@router.post("/sizing", response_model=SizingResultOut, status_code=status.HTTP_201_CREATED)
async def compute_sizing(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("company_profile.manage")),
    sizing_service: SizingEngineService = Depends(get_sizing_engine_service),
):
    """docs/adaptive/04-erp-sizing-engine-spec.md. Deterministic: computing
    this again for the same profile against the same active rule_version
    always returns the same dimension_scores -- each call still creates a
    new, immutable SizingResult row (never overwrites a prior one), so the
    history of "what did sizing say, and when" is never lost."""
    try:
        result = await sizing_service.compute(tenant_id=ctx.tenant_id, company_id=ctx.company_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    await db.commit()
    return result


@router.get("/sizing/latest", response_model=SizingResultOut)
async def get_latest_sizing(
    ctx: AuthContext = Depends(require_permission("company_profile.view")),
    sizing_service: SizingEngineService = Depends(get_sizing_engine_service),
):
    result = await sizing_service.get_latest(company_id=ctx.company_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No sizing result exists for this company yet")
    return result


@router.post("/blueprint", response_model=ErpBlueprintOut, status_code=status.HTTP_201_CREATED)
async def generate_blueprint(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("configuration.blueprint.generate")),
    blueprint_service: BlueprintService = Depends(get_blueprint_service),
):
    """docs/adaptive/05-erp-blueprint-spec.md. Generates a new draft
    Blueprint from the company's latest SizingResult -- generation never
    approves itself, and never mutates business data (see BlueprintService
    docstring)."""
    try:
        blueprint = await blueprint_service.generate(
            tenant_id=ctx.tenant_id, company_id=ctx.company_id, user_id=ctx.user_id
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    await db.commit()
    return blueprint


@router.get("/blueprint/latest", response_model=ErpBlueprintOut)
async def get_latest_blueprint(
    ctx: AuthContext = Depends(require_permission("configuration.blueprint.view")),
    blueprint_service: BlueprintService = Depends(get_blueprint_service),
):
    blueprint = await blueprint_service.get_latest(company_id=ctx.company_id)
    if blueprint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No Blueprint exists for this company yet")
    return blueprint


@router.get("/blueprint", response_model=list[ErpBlueprintOut])
async def list_blueprints(
    ctx: AuthContext = Depends(require_permission("configuration.blueprint.view")),
    blueprint_service: BlueprintService = Depends(get_blueprint_service),
):
    return await blueprint_service.list_for_company(company_id=ctx.company_id)


@router.get("/blueprint/{blueprint_id}", response_model=ErpBlueprintOut)
async def get_blueprint(
    blueprint_id: UUID,
    ctx: AuthContext = Depends(require_permission("configuration.blueprint.view")),
    blueprint_service: BlueprintService = Depends(get_blueprint_service),
):
    blueprint = await blueprint_service.get(blueprint_id=blueprint_id)
    if blueprint is None or blueprint.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blueprint not found")
    return blueprint


@router.post("/blueprint/{blueprint_id}/approve", response_model=ErpBlueprintOut)
async def approve_blueprint(
    blueprint_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("configuration.blueprint.approve")),
    blueprint_service: BlueprintService = Depends(get_blueprint_service),
):
    """Approving a Blueprint automatically supersedes whatever was
    previously the sole approved Blueprint for this company -- never
    deleted, never mutated in place (docs/adaptive/05 §5.3)."""
    try:
        blueprint = await blueprint_service.approve(
            company_id=ctx.company_id, blueprint_id=blueprint_id, user_id=ctx.user_id
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e

    await db.commit()
    return blueprint


@router.post("/configuration-plan", response_model=ConfigurationPlanOut, status_code=status.HTTP_201_CREATED)
async def create_configuration_plan(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("configuration.plan.create")),
    engine: ConfigurationEngineService = Depends(get_configuration_engine_service),
):
    """Stage 2.4 v1 (Design & Safety Review). company_id is taken only from
    the approved Blueprint (never client-supplied); at most one Plan can
    ever exist per (company, blueprint) pair -- DB UniqueConstraint plus a
    pre-check here."""
    try:
        plan = await engine.create_plan(tenant_id=ctx.tenant_id, company_id=ctx.company_id, user_id=ctx.user_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e

    items = await engine.list_items(plan_id=plan.id)
    await db.commit()
    return _plan_out(plan, items)


@router.post("/configuration-plan/{plan_id}/validate", response_model=ConfigurationPlanOut)
async def validate_configuration_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("configuration.plan.create")),
    engine: ConfigurationEngineService = Depends(get_configuration_engine_service),
):
    try:
        plan = await engine.validate(plan_id=plan_id, company_id=ctx.company_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e

    items = await engine.list_items(plan_id=plan.id)
    await db.commit()
    return _plan_out(plan, items)


@router.post("/configuration-plan/{plan_id}/apply", response_model=ConfigurationPlanOut)
async def apply_configuration_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("configuration.plan.apply")),
    engine: ConfigurationEngineService = Depends(get_configuration_engine_service),
):
    """Re-checks the source Blueprint is still 'approved' immediately
    before writing, every call -- including idempotent re-runs on an
    already-applied Plan. A failure mid-Apply rolls back every write made
    in this attempt via a nested transaction; only the failure record
    itself survives (Stage 2.4 Design & Safety Review §3.2/§3.3)."""
    try:
        plan = await engine.apply(
            plan_id=plan_id, tenant_id=ctx.tenant_id, company_id=ctx.company_id, user_id=ctx.user_id
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e

    items = await engine.list_items(plan_id=plan.id)
    await db.commit()
    return _plan_out(plan, items)


@router.get("/configuration-plan/latest", response_model=ConfigurationPlanOut)
async def get_latest_configuration_plan(
    ctx: AuthContext = Depends(require_permission("configuration.plan.view")),
    engine: ConfigurationEngineService = Depends(get_configuration_engine_service),
):
    plans = await engine.list_for_company(company_id=ctx.company_id)
    if not plans:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No Configuration Plan exists for this company yet")
    plan = plans[0]
    items = await engine.list_items(plan_id=plan.id)
    return _plan_out(plan, items)


@router.get("/configuration-plan", response_model=list[ConfigurationPlanOut])
async def list_configuration_plans(
    ctx: AuthContext = Depends(require_permission("configuration.plan.view")),
    engine: ConfigurationEngineService = Depends(get_configuration_engine_service),
):
    plans = await engine.list_for_company(company_id=ctx.company_id)
    return [_plan_out(plan, await engine.list_items(plan_id=plan.id)) for plan in plans]


@router.get("/configuration-plan/{plan_id}", response_model=ConfigurationPlanOut)
async def get_configuration_plan(
    plan_id: UUID,
    ctx: AuthContext = Depends(require_permission("configuration.plan.view")),
    engine: ConfigurationEngineService = Depends(get_configuration_engine_service),
):
    plan = await engine.get(plan_id=plan_id)
    if plan is None or plan.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Configuration Plan not found")
    items = await engine.list_items(plan_id=plan.id)
    return _plan_out(plan, items)
