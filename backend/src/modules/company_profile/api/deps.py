"""FastAPI dependencies for Company Profile (Adaptive ERP Stage 2.1)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.company_profile.application.services import CompanyProfileService
from src.modules.company_profile.infrastructure.repositories import CompanyProfileRepository
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
