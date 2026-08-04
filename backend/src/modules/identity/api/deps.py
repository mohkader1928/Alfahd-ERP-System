"""FastAPI dependencies for the Identity module: DB-session-bound repositories
and the RBAC permission-check dependency (FR-CORE-014/015)."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.infrastructure.repositories import (
    AuditLogRepository,
    BranchRepository,
    CompanyRepository,
    CurrencyRepository,
    PartnerAddressRepository,
    PartnerRepository,
    ProductCategoryRepository,
    ProductRepository,
    RoleRepository,
    UnitOfMeasureRepository,
    UserRepository,
)
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext, get_auth_context, require_branch_context


def get_company_repo(db: AsyncSession = Depends(get_db)) -> CompanyRepository:
    return CompanyRepository(db)


def get_branch_repo(db: AsyncSession = Depends(get_db)) -> BranchRepository:
    return BranchRepository(db)


def get_currency_repo(db: AsyncSession = Depends(get_db)) -> CurrencyRepository:
    return CurrencyRepository(db)


def get_user_repo(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_role_repo(db: AsyncSession = Depends(get_db)) -> RoleRepository:
    return RoleRepository(db)


def get_partner_repo(db: AsyncSession = Depends(get_db)) -> PartnerRepository:
    return PartnerRepository(db)


def get_partner_address_repo(db: AsyncSession = Depends(get_db)) -> PartnerAddressRepository:
    return PartnerAddressRepository(db)


def get_product_repo(db: AsyncSession = Depends(get_db)) -> ProductRepository:
    return ProductRepository(db)


def get_audit_log_repo(db: AsyncSession = Depends(get_db)) -> AuditLogRepository:
    return AuditLogRepository(db)


def get_product_category_repo(db: AsyncSession = Depends(get_db)) -> ProductCategoryRepository:
    return ProductCategoryRepository(db)


def get_uom_repo(db: AsyncSession = Depends(get_db)) -> UnitOfMeasureRepository:
    return UnitOfMeasureRepository(db)


def require_permission(permission_code: str, *, require_branch: bool = False):
    """Dependency factory: `Depends(require_permission("company.manage_branches"))`.

    Screen/action-level RBAC per FR-CORE-015/017. Field-level permission
    filtering (FR-CORE-016) and Record Rules (FR-CORE-017) are enforced
    separately inside each application service where the relevant fields/
    records are known — not generic enough to belong in this dependency.

    `require_branch=True` additionally rejects requests with no X-Branch-Id
    (FR-CORE-002) — use for any endpoint that creates a branch-scoped
    document (sales/purchasing/inventory documents).
    """
    auth_dependency = require_branch_context if require_branch else get_auth_context

    async def _check(
        ctx: AuthContext = Depends(auth_dependency),
        role_repo: RoleRepository = Depends(get_role_repo),
    ) -> AuthContext:
        granted = await role_repo.get_user_permission_codes(ctx.user_id, ctx.company_id)
        if permission_code not in granted:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission_code}")
        return ctx

    return _check
