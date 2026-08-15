"""FastAPI routes for Company Profile (Adaptive ERP Stage 2.1).

See docs/adaptive/03-customer-profile-spec.md for the field-by-field
justification and docs/adaptive/06-configuration-engine-architecture.md
§6.6 for the security posture (same RLS + require_permission mechanism as
every other module — no new isolation or auth mechanism introduced here).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.company_profile.api.deps import (
    get_company_profile_repo,
    get_company_profile_service,
    require_permission,
)
from src.modules.company_profile.api.schemas import CompanyProfileOut, CompanyProfileWriteRequest
from src.modules.company_profile.application.services import CompanyProfileService
from src.modules.company_profile.infrastructure.repositories import CompanyProfileRepository
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext

router = APIRouter()


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
