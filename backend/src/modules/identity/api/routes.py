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
    get_product_category_repo,
    get_product_repo,
    get_role_repo,
    get_uom_repo,
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
    MyPermissionsOut,
    PartnerCreateRequest,
    PartnerOut,
    PartnerUpdateRequest,
    ProductCategoryCreateRequest,
    ProductCategoryOut,
    ProductCategoryUpdateRequest,
    ProductCreateRequest,
    ProductOut,
    ProductUpdateRequest,
    RoleAssignRequest,
    TokenResponse,
    TwoFactorLoginRequest,
    TwoFactorRequiredResponse,
    UnitOfMeasureCreateRequest,
    UnitOfMeasureOut,
    UnitOfMeasureUpdateRequest,
    UserCreateRequest,
    UserOut,
)
from src.modules.identity.application.services import (
    AuthenticationError,
    AuthenticationService,
    CompanyRegistrationService,
    PartnerService,
    ProductCategoryService,
    ProductService,
    TenantProvisioningService,
    TwoFactorRequiredError,
    UnitOfMeasureService,
    UserManagementService,
)
from src.modules.identity.domain.events import CompanyRegistered
from src.modules.identity.infrastructure.repositories import (
    AuditLogRepository,
    BranchRepository,
    CompanyRepository,
    CurrencyRepository,
    PartnerRepository,
    ProductCategoryRepository,
    ProductRepository,
    RoleRepository,
    UnitOfMeasureRepository,
    UserRepository,
)
from src.shared.infrastructure.db.session import (
    get_db,
    set_company_context,
    set_login_lookup,
    set_tenant_context,
)
from src.shared.infrastructure.messaging.event_bus import event_bus
from src.shared.security.auth_context import AuthContext, get_auth_context

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

    # Phase 17C-RLS: `role` and `user_company_access` (below) are
    # company_isolation-policy tables, not tenant_isolation — the tenant
    # context set above isn't enough for their WITH CHECK clause. This was
    # invisible while the API connected as the erp superuser (bypasses RLS
    # unconditionally); erp_app does not bypass it.
    await set_company_context(db, company.id)

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
        # Phase 17C-RLS Step 3A: the tenant isn't known until after this
        # by-email lookup finds the user — see app_user_login_lookup policy
        # (migration f7004fe055a4) and set_login_lookup()'s docstring.
        await set_login_lookup(db)
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
        # Phase 17C-RLS Step 3A: same rationale as the login endpoint above.
        await set_login_lookup(db)
        user = await auth_service.authenticate_step2_totp(
            email=payload.email, plain_password=payload.password, totp_code=payload.totp_code
        )
    except AuthenticationError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    tokens = await auth_service.issue_tokens(user)
    return TokenResponse(**tokens)


@router.get("/me/permissions", response_model=MyPermissionsOut)
async def get_my_permissions(
    ctx: AuthContext = Depends(get_auth_context),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    """Phase 17A: read-only, self-scoped — any authenticated caller may
    always see their own granted permissions for the active company. No
    `require_permission()` guard is applicable here since there is no
    action being gated other than reading one's own grants."""
    codes = await role_repo.get_user_permission_codes(ctx.user_id, ctx.company_id)
    return MyPermissionsOut(permission_codes=sorted(codes))


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
    search: str | None = None,
    ctx: AuthContext = Depends(require_permission("partner.view")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    return await partner_repo.list_by_company(
        ctx.company_id, customers_only=customers_only, vendors_only=vendors_only, search=search
    )


@router.get("/partners/{partner_id}", response_model=PartnerOut)
async def get_partner(
    partner_id: UUID,
    ctx: AuthContext = Depends(require_permission("partner.view")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    # partner_repo.get_by_id() is shared with Sales/Purchasing/the ZATCA
    # worker and isn't itself company-scoped (changing its signature would
    # ripple across those call sites, out of scope here) — RLS is *meant*
    # to close that gap at the DB layer, but do not rely on RLS alone: an
    # explicit company_id check is the actual boundary for this new route.
    partner = await partner_repo.get_by_id(partner_id)
    if partner is None or partner.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
    return partner


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
            address=payload.address.model_dump() if payload.address else None,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return partner


@router.patch("/partners/{partner_id}", response_model=PartnerOut)
async def update_partner(
    partner_id: UUID,
    payload: PartnerUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("partner.update")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    service = PartnerService(partner_repo)
    try:
        partner = await service.update_partner(
            company_id=ctx.company_id,
            partner_id=partner_id,
            name=payload.name,
            name_ar=payload.name_ar,
            is_customer=payload.is_customer,
            is_vendor=payload.is_vendor,
            vat_number=payload.vat_number,
            cr_number=payload.cr_number,
            address=payload.address.model_dump() if payload.address else None,
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return partner


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    category_id: UUID | None = None,
    search: str | None = None,
    ctx: AuthContext = Depends(require_permission("product.view")),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    return await product_repo.list_by_company(ctx.company_id, category_id=category_id, search=search)


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: UUID,
    ctx: AuthContext = Depends(require_permission("product.view")),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    # See the same note on get_partner() above — explicit check, not RLS alone.
    product = await product_repo.get_by_id(product_id)
    if product is None or product.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("product.create")),
    product_repo: ProductRepository = Depends(get_product_repo),
    category_repo: ProductCategoryRepository = Depends(get_product_category_repo),
    uom_repo: UnitOfMeasureRepository = Depends(get_uom_repo),
):
    service = ProductService(product_repo, category_repo, uom_repo)
    try:
        product = await service.create_product(
            tenant_id=ctx.tenant_id,
            company_id=ctx.company_id,
            sku=payload.sku,
            name=payload.name,
            name_ar=payload.name_ar,
            category_id=payload.category_id,
            uom_id=payload.uom_id,
            is_stockable=payload.is_stockable,
            sales_price=payload.sales_price,
            cost_price=payload.cost_price,
            default_tax_rate_id=payload.default_tax_rate_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: UUID,
    payload: ProductUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("product.update")),
    product_repo: ProductRepository = Depends(get_product_repo),
    category_repo: ProductCategoryRepository = Depends(get_product_category_repo),
    uom_repo: UnitOfMeasureRepository = Depends(get_uom_repo),
):
    service = ProductService(product_repo, category_repo, uom_repo)
    try:
        product = await service.update_product(
            company_id=ctx.company_id,
            product_id=product_id,
            sku=payload.sku,
            name=payload.name,
            name_ar=payload.name_ar,
            category_id=payload.category_id,
            uom_id=payload.uom_id,
            is_stockable=payload.is_stockable,
            sales_price=payload.sales_price,
            cost_price=payload.cost_price,
            default_tax_rate_id=payload.default_tax_rate_id,
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return product


@router.get("/product-categories", response_model=list[ProductCategoryOut])
async def list_product_categories(
    ctx: AuthContext = Depends(require_permission("product_category.view")),
    category_repo: ProductCategoryRepository = Depends(get_product_category_repo),
):
    """Returns the flat list for the company; the frontend assembles the
    tree client-side (Phase 17B design decision — one query, no N+1, and
    trivially fast at realistic category counts)."""
    return await category_repo.list_by_company(ctx.company_id)


@router.get("/product-categories/{category_id}", response_model=ProductCategoryOut)
async def get_product_category(
    category_id: UUID,
    ctx: AuthContext = Depends(require_permission("product_category.view")),
    category_repo: ProductCategoryRepository = Depends(get_product_category_repo),
):
    category = await category_repo.get_by_id(ctx.company_id, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product category not found")
    return category


@router.post("/product-categories", response_model=ProductCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_product_category(
    payload: ProductCategoryCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("product_category.manage")),
    category_repo: ProductCategoryRepository = Depends(get_product_category_repo),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    service = ProductCategoryService(category_repo, product_repo)
    try:
        category = await service.create_category(
            company_id=ctx.company_id, name=payload.name, parent_id=payload.parent_id
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return category


@router.patch("/product-categories/{category_id}", response_model=ProductCategoryOut)
async def update_product_category(
    category_id: UUID,
    payload: ProductCategoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("product_category.manage")),
    category_repo: ProductCategoryRepository = Depends(get_product_category_repo),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    service = ProductCategoryService(category_repo, product_repo)
    try:
        category = await service.update_category(
            company_id=ctx.company_id, category_id=category_id, name=payload.name, parent_id=payload.parent_id
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return category


@router.delete("/product-categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("product_category.manage")),
    category_repo: ProductCategoryRepository = Depends(get_product_category_repo),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    service = ProductCategoryService(category_repo, product_repo)
    try:
        await service.delete_category(company_id=ctx.company_id, category_id=category_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()


@router.get("/uom", response_model=list[UnitOfMeasureOut])
async def list_uom(
    active: bool | None = None,
    search: str | None = None,
    ctx: AuthContext = Depends(require_permission("uom.view")),
    uom_repo: UnitOfMeasureRepository = Depends(get_uom_repo),
):
    return await uom_repo.list_by_company(ctx.company_id, active=active, search=search)


@router.get("/uom/{uom_id}", response_model=UnitOfMeasureOut)
async def get_uom(
    uom_id: UUID,
    ctx: AuthContext = Depends(require_permission("uom.view")),
    uom_repo: UnitOfMeasureRepository = Depends(get_uom_repo),
):
    uom = await uom_repo.get_by_id(ctx.company_id, uom_id)
    if uom is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unit of measure not found")
    return uom


@router.post("/uom", response_model=UnitOfMeasureOut, status_code=status.HTTP_201_CREATED)
async def create_uom(
    payload: UnitOfMeasureCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("uom.manage")),
    uom_repo: UnitOfMeasureRepository = Depends(get_uom_repo),
):
    service = UnitOfMeasureService(uom_repo)
    try:
        uom = await service.create_uom(
            company_id=ctx.company_id, name=payload.name, code=payload.code, name_ar=payload.name_ar
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return uom


@router.patch("/uom/{uom_id}", response_model=UnitOfMeasureOut)
async def update_uom(
    uom_id: UUID,
    payload: UnitOfMeasureUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("uom.manage")),
    uom_repo: UnitOfMeasureRepository = Depends(get_uom_repo),
):
    """Also the deactivate operation — PATCH with `active: false`. No hard
    DELETE endpoint exists for UOM (Phase 17B decision): existing
    `product.uom_id` foreign keys must never be able to dangle."""
    service = UnitOfMeasureService(uom_repo)
    try:
        uom = await service.update_uom(
            company_id=ctx.company_id,
            uom_id=uom_id,
            name=payload.name,
            code=payload.code,
            name_ar=payload.name_ar,
            active=payload.active,
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return uom


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
