"""FastAPI routes for the Identity module, per Phase 10 §6.1."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.api.deps import (
    get_audit_log_repo,
    get_branch_repo,
    get_company_repo,
    get_currency_repo,
    get_partner_repo,
    get_product_repo,
    get_role_repo,
    get_user_repo,
    require_permission,
)
from src.modules.identity.api.schemas import (
    AuditLogOut,
    BootstrapRequest,
    BootstrapResponse,
    BranchCreateRequest,
    BranchOut,
    CompanyOut,
    LoginRequest,
    PartnerCreateRequest,
    PartnerOut,
    ProductCreateRequest,
    ProductOut,
    RoleAssignRequest,
    TokenResponse,
    TwoFactorLoginRequest,
    TwoFactorRequiredResponse,
    UserCreateRequest,
    UserOut,
)
from src.modules.identity.application.services import (
    AuthenticationError,
    AuthenticationService,
    CompanyRegistrationService,
    PartnerService,
    ProductService,
    TenantProvisioningService,
    TwoFactorRequiredError,
    UserManagementService,
)
from src.modules.identity.domain.events import CompanyRegistered
from src.modules.identity.infrastructure.repositories import (
    AuditLogRepository,
    BranchRepository,
    CompanyRepository,
    CurrencyRepository,
    PartnerRepository,
    ProductRepository,
    RoleRepository,
    UserRepository,
)
from src.shared.infrastructure.db.session import get_db, set_tenant_context
from src.shared.infrastructure.messaging.event_bus import event_bus
from src.shared.security.auth_context import AuthContext

router = APIRouter()


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap(
    payload: BootstrapRequest,
    db: AsyncSession = Depends(get_db),
    company_repo: CompanyRepository = Depends(get_company_repo),
    branch_repo: BranchRepository = Depends(get_branch_repo),
    currency_repo: CurrencyRepository = Depends(get_currency_repo),
    user_repo: UserRepository = Depends(get_user_repo),
    role_repo: RoleRepository = Depends(get_role_repo),
) -> BootstrapResponse:
    """One-time setup: create Tenant + Company + Branch + first Admin user
    with a full-access Role. No auth required (there is nothing to
    authenticate against yet) — this is the only unauthenticated write
    endpoint in the system by design, and should be disabled/removed once
    provisioning is handled by an internal admin tool (out of nucleus scope).
    """
    tenant_service = TenantProvisioningService(db)
    tenant = await tenant_service.create_tenant(payload.tenant_legal_name)

    # RLS policies (Phase 7 §1.4) reject inserts unless app.current_tenant_id
    # is set for the transaction. Every other endpoint gets this from
    # get_auth_context() via the caller's JWT; bootstrap has no JWT yet
    # because it creates the very first tenant, so it sets its own context
    # immediately after minting the tenant it will insert data under.
    await set_tenant_context(db, tenant.id)

    company_service = CompanyRegistrationService(company_repo, branch_repo, currency_repo)
    try:
        company, branch = await company_service.register_company(
            tenant_id=tenant.id,
            legal_name=payload.company_legal_name,
            legal_name_ar=payload.company_legal_name_ar,
            vat_number=payload.vat_number,
            base_currency_code=payload.base_currency_code,
            valuation_method=payload.valuation_method,
            main_branch_name=payload.main_branch_name,
            main_branch_name_ar=payload.main_branch_name_ar,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    user_service = UserManagementService(user_repo, role_repo)
    try:
        admin_user = await user_service.create_user(
            tenant_id=tenant.id,
            email=payload.admin_email,
            full_name=payload.admin_full_name,
            plain_password=payload.admin_password,
            company_id=company.id,
            branch_id=branch.id,
        )
        from src.shared.infrastructure.db.seed import PERMISSION_CATALOG

        admin_role = await user_service.create_role(
            company_id=company.id,
            name="Admin",
            permission_codes=[code for code, _ in PERMISSION_CATALOG],
        )
        await user_service.assign_role(user_id=admin_user.id, role_id=admin_role.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()

    # Notify other modules a company now exists (Phase 8 §3/§7 — Domain
    # Events). Accounting listens for this to seed the default Saudi Chart
    # of Accounts; Identity itself has zero knowledge of Accounting, per the
    # module dependency map.
    await event_bus.publish(
        CompanyRegistered(tenant_id=tenant.id, company_id=company.id, valuation_method=payload.valuation_method)
    )

    return BootstrapResponse(
        tenant_id=tenant.id,
        company_id=company.id,
        branch_id=branch.id,
        admin_user_id=admin_user.id,
        admin_role_id=admin_role.id,
    )


@router.post("/auth/login", response_model=TokenResponse | TwoFactorRequiredResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db), user_repo: UserRepository = Depends(get_user_repo)):
    auth_service = AuthenticationService(user_repo)
    try:
        user = await auth_service.authenticate_step1(email=payload.email, plain_password=payload.password)
    except TwoFactorRequiredError:
        return TwoFactorRequiredResponse()
    except AuthenticationError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    tokens = await auth_service.issue_tokens(user)
    return TokenResponse(**tokens)


@router.post("/auth/login/verify-2fa", response_model=TokenResponse)
async def verify_2fa(
    payload: TwoFactorLoginRequest,
    db: AsyncSession = Depends(get_db),
    user_repo: UserRepository = Depends(get_user_repo),
):
    auth_service = AuthenticationService(user_repo)
    try:
        user = await auth_service.authenticate_step2_totp(
            email=payload.email, plain_password=payload.password, totp_code=payload.totp_code
        )
    except AuthenticationError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    tokens = await auth_service.issue_tokens(user)
    return TokenResponse(**tokens)


@router.get("/companies/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: UUID,
    ctx: AuthContext = Depends(require_permission("company.view")),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    company = await company_repo.get_by_id(ctx.company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company


@router.post("/companies/{company_id}/branches", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
async def create_branch(
    company_id: UUID,
    payload: BranchCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("company.manage_branches")),
    branch_repo: BranchRepository = Depends(get_branch_repo),
):
    import uuid as _uuid

    from src.modules.identity.infrastructure.models import Branch

    branch = Branch(
        id=_uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        name=payload.name,
        name_ar=payload.name_ar,
        is_main=payload.is_main,
    )
    await branch_repo.add(branch)
    await db.commit()
    return branch


@router.get("/companies/{company_id}/branches", response_model=list[BranchOut])
async def list_branches(
    company_id: UUID,
    ctx: AuthContext = Depends(require_permission("company.view")),
    branch_repo: BranchRepository = Depends(get_branch_repo),
):
    return await branch_repo.list_by_company(ctx.company_id)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("user.create")),
    user_repo: UserRepository = Depends(get_user_repo),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    user_service = UserManagementService(user_repo, role_repo)
    try:
        user = await user_service.create_user(
            tenant_id=ctx.tenant_id,
            email=payload.email,
            full_name=payload.full_name,
            plain_password=payload.password,
            company_id=payload.company_id,
            branch_id=payload.branch_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return user


@router.post("/users/{user_id}/roles", status_code=status.HTTP_204_NO_CONTENT)
async def assign_role(
    user_id: UUID,
    payload: RoleAssignRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("user.manage_roles")),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    await role_repo.assign_to_user(user_id=user_id, role_id=payload.role_id)
    await AuditLogRepository(db).record(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        target_table="user_role",
        target_id=user_id,
        field_name="role_id",
        old_value=None,
        new_value=str(payload.role_id),
    )
    await db.commit()


@router.get("/partners", response_model=list[PartnerOut])
async def list_partners(
    customers_only: bool = False,
    vendors_only: bool = False,
    ctx: AuthContext = Depends(require_permission("partner.view")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    return await partner_repo.list_by_company(ctx.company_id, customers_only=customers_only, vendors_only=vendors_only)


@router.post("/partners", response_model=PartnerOut, status_code=status.HTTP_201_CREATED)
async def create_partner(
    payload: PartnerCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("partner.create")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    service = PartnerService(partner_repo)
    try:
        partner = await service.create_partner(
            tenant_id=ctx.tenant_id,
            company_id=ctx.company_id,
            name=payload.name,
            name_ar=payload.name_ar,
            is_customer=payload.is_customer,
            is_vendor=payload.is_vendor,
            vat_number=payload.vat_number,
            cr_number=payload.cr_number,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return partner


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    ctx: AuthContext = Depends(require_permission("product.view")),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    return await product_repo.list_by_company(ctx.company_id)


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("product.create")),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    service = ProductService(product_repo)
    try:
        product = await service.create_product(
            tenant_id=ctx.tenant_id,
            company_id=ctx.company_id,
            sku=payload.sku,
            name=payload.name,
            name_ar=payload.name_ar,
            is_stockable=payload.is_stockable,
            sales_price=payload.sales_price,
            cost_price=payload.cost_price,
            default_tax_rate_id=payload.default_tax_rate_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return product


@router.get("/audit-log", response_model=list[AuditLogOut])
async def list_audit_log(
    target_table: str | None = None,
    user_id: UUID | None = None,
    limit: int = 100,
    ctx: AuthContext = Depends(require_permission("audit_log.view")),
    audit_log_repo: AuditLogRepository = Depends(get_audit_log_repo),
):
    """FR-RPT-004 — filterable audit trail report."""
    return await audit_log_repo.list_by_company(
        ctx.company_id, target_table=target_table, user_id=user_id, limit=min(limit, 500)
    )
