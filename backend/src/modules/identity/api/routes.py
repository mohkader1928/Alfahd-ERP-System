"""FastAPI routes for the Identity module, per Phase 10 §6.1."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.api.deps import (
    get_audit_log_repo,
    get_branch_repo,
    get_company_repo,
    get_currency_repo,
    get_partner_address_repo,
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
    CompanyAccessGrantRequest,
    CompanyAccessRow,
    CompanyCreateRequest,
    CompanyOut,
    CompanyUpdateRequest,
    LoginRequest,
    MyPermissionsOut,
    PartnerAddressCreateRequest,
    PartnerAddressOut,
    PartnerAddressUpdateRequest,
    PartnerCreateRequest,
    PartnerOut,
    PartnerUpdateRequest,
    PermissionOut,
    ProductCategoryCreateRequest,
    ProductCategoryOut,
    ProductCategoryUpdateRequest,
    ProductCreateRequest,
    ProductOut,
    ProductUpdateRequest,
    RoleAssignRequest,
    RoleCreateRequest,
    RoleDetailOut,
    RoleOut,
    RolePermissionsUpdateRequest,
    RoleRenameRequest,
    TokenResponse,
    TwoFactorLoginRequest,
    TwoFactorRequiredResponse,
    UnitOfMeasureCreateRequest,
    UnitOfMeasureOut,
    UnitOfMeasureUpdateRequest,
    UserCreateRequest,
    UserDetailOut,
    UserListRow,
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
    PartnerAddressRepository,
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
from src.shared.media.storage import InvalidImageError, delete_entity_image, save_entity_image
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

    user_service = UserManagementService(user_repo, role_repo, company_repo)
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
            is_system=True,
        )
        await user_service.assign_role(user_id=admin_user.id, role_id=admin_role.id)
        # P0-6 (3-Day Brief): real separation-of-duties roles the Owner can
        # assign immediately, not just one all-powerful login — see
        # seed_default_role_templates's own docstring for why these are
        # ordinary (editable/deletable) roles, unlike Admin above.
        await user_service.seed_default_role_templates(company_id=company.id)
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


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("company.create")),
    company_repo: CompanyRepository = Depends(get_company_repo),
    branch_repo: BranchRepository = Depends(get_branch_repo),
    currency_repo: CurrencyRepository = Depends(get_currency_repo),
    user_repo: UserRepository = Depends(get_user_repo),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    """UI/UX Foundation milestone (explicitly approved by the Owner):
    before this, /bootstrap was the only way to create a company, and it
    always mints a brand-new tenant alongside it — there was no way to add
    a second company to an already-existing tenant, which blocked building
    a genuine multi-company acceptance test for the new Company Context
    picker. Reuses the same, already-tested CompanyRegistrationService
    bootstrap itself uses; the new company always lands in the caller's
    own tenant (ctx.tenant_id), never an arbitrary one.

    Also provisions the caller as this company's Admin (same "Admin" role
    shape /bootstrap creates — full current permission catalog — plus a
    company-access grant), because without it the new company would have
    zero roles and be unusable by anyone: unlike /bootstrap, there is no
    other API path today to create a role for an existing company. This
    was found live while building the two-company acceptance scenario
    (granting bare company access alone still 403'd on every real screen,
    since access and permissions are separate)."""
    company_service = CompanyRegistrationService(company_repo, branch_repo, currency_repo)
    try:
        company, _branch = await company_service.register_company(
            tenant_id=ctx.tenant_id,
            legal_name=payload.legal_name,
            legal_name_ar=payload.legal_name_ar,
            vat_number=payload.vat_number,
            base_currency_code=payload.base_currency_code,
            valuation_method=payload.valuation_method,
            main_branch_name=payload.main_branch_name,
            main_branch_name_ar=payload.main_branch_name_ar,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    # role/user_role/user_company_access carry company_isolation RLS keyed
    # off the new company, not the caller's currently active one.
    await set_company_context(db, company.id)

    user_service = UserManagementService(user_repo, role_repo, company_repo)
    try:
        from src.shared.infrastructure.db.seed import PERMISSION_CATALOG

        admin_role = await user_service.create_role(
            company_id=company.id,
            name="Admin",
            permission_codes=[code for code, _ in PERMISSION_CATALOG],
            is_system=True,
        )
        await user_service.assign_role(user_id=ctx.user_id, role_id=admin_role.id)
        await user_service.grant_company_access(
            tenant_id=ctx.tenant_id, user_id=ctx.user_id, company_id=company.id, branch_id=None
        )
        await user_service.seed_default_role_templates(company_id=company.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    await set_company_context(db, ctx.company_id)

    # Same as /bootstrap: Accounting listens for this to seed the default
    # Saudi Chart of Accounts, tax rates, etc. for the new company —
    # without it, this company would be structurally incomplete compared
    # to every other company in the system.
    await event_bus.publish(
        CompanyRegistered(tenant_id=ctx.tenant_id, company_id=company.id, valuation_method=payload.valuation_method)
    )

    return company


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


@router.patch("/companies/{company_id}", response_model=CompanyOut)
async def update_company(
    company_id: UUID,
    payload: CompanyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("company.manage")),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """Settings Architecture Foundation milestone. The first endpoint able
    to edit a company's own core details at all — until now legal_name/
    legal_name_ar/vat_number/cr_number were fixed at /bootstrap time with no
    way to correct them, a real gap surfaced while building the Company
    Profile screen (that screen showed these fields read-only specifically
    because this endpoint didn't exist yet)."""
    company = await company_repo.get_by_id(ctx.company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    old_values = {
        "legal_name": company.legal_name,
        "legal_name_ar": company.legal_name_ar,
        "vat_number": company.vat_number,
        "cr_number": company.cr_number,
        "po_approval_threshold": company.po_approval_threshold,
    }
    company.legal_name = payload.legal_name
    company.legal_name_ar = payload.legal_name_ar
    company.vat_number = payload.vat_number
    company.cr_number = payload.cr_number
    company.po_approval_threshold = payload.po_approval_threshold

    audit_repo = AuditLogRepository(db)
    new_values = {
        "legal_name": company.legal_name,
        "legal_name_ar": company.legal_name_ar,
        "vat_number": company.vat_number,
        "cr_number": company.cr_number,
        "po_approval_threshold": company.po_approval_threshold,
    }
    try:
        for field_name, old_value in old_values.items():
            new_value = new_values[field_name]
            if old_value != new_value:
                await audit_repo.record(
                    tenant_id=ctx.tenant_id,
                    company_id=ctx.company_id,
                    user_id=ctx.user_id,
                    target_table="company",
                    target_id=company.id,
                    field_name=field_name,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                )
        # No db.refresh(): same RLS/transaction-scoping reason documented on
        # upload_company_logo() below — company already reflects the new
        # values in memory, and the response schema needs no server-generated
        # column a refresh would add.
        await db.commit()
    except IntegrityError as e:
        # ux_company_vat is global (not per-company), so a duplicate on
        # another company's row is invisible to a plain SELECT under this
        # request's RLS context (other companies aren't visible) — the
        # unique index itself is the only thing that actually catches it,
        # found live via this endpoint's own test.
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "VAT number already in use") from e
    return company


@router.post("/companies/{company_id}/logo", response_model=CompanyOut)
async def upload_company_logo(
    company_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("company.manage")),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """Entity Media Foundation. Mirrors get_company()'s existing precedent
    of operating on the caller's active company (ctx.company_id) rather
    than trusting the path segment — same resource, same convention."""
    company = await company_repo.get_by_id(ctx.company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    try:
        relative_path = await save_entity_image(file, entity_type="company", entity_id=str(company.id))
    except InvalidImageError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    old_path = company.logo_path
    company.logo_path = relative_path
    # No db.refresh() here: `company.logo_path` is already set on this
    # in-memory instance above, and a post-commit refresh would issue a
    # fresh SELECT outside the transaction that carried the RLS
    # SET LOCAL app.current_company_id — found live via this endpoint's own
    # test, where that follow-up SELECT failed RLS with an empty session
    # variable. The response schema doesn't need any server-generated
    # column (e.g. updated_at) that only a refresh would pick up.
    await db.commit()
    delete_entity_image(old_path)
    return company


@router.delete("/companies/{company_id}/logo", response_model=CompanyOut)
async def delete_company_logo(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("company.manage")),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    company = await company_repo.get_by_id(ctx.company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    old_path = company.logo_path
    company.logo_path = None
    # No db.refresh() here: `company.logo_path` is already set on this
    # in-memory instance above, and a post-commit refresh would issue a
    # fresh SELECT outside the transaction that carried the RLS
    # SET LOCAL app.current_company_id — found live via this endpoint's own
    # test, where that follow-up SELECT failed RLS with an empty session
    # variable. The response schema doesn't need any server-generated
    # column (e.g. updated_at) that only a refresh would pick up.
    await db.commit()
    delete_entity_image(old_path)
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


@router.get("/users", response_model=list[UserListRow])
async def list_users(
    ctx: AuthContext = Depends(require_permission("user.view")),
    user_repo: UserRepository = Depends(get_user_repo),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    """Bundle 2 — Identity/Access/Governance: the Owner-facing gap found
    during the full-project re-audit. `POST /users` and role/company-access
    grants already existed but had zero way to list who's already been
    created — an owner could not add a second real employee through the
    product at all."""
    users = await user_repo.list_by_company_access(ctx.company_id)
    rows = []
    for user in users:
        roles = await role_repo.list_for_user_in_company(user.id, ctx.company_id)
        rows.append(
            UserListRow(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                is_2fa_enabled=user.is_2fa_enabled,
                role_names=[r.name for r in roles],
            )
        )
    return rows


@router.get("/users/{user_id}", response_model=UserDetailOut)
async def get_user(
    user_id: UUID,
    ctx: AuthContext = Depends(require_permission("user.view")),
    user_repo: UserRepository = Depends(get_user_repo),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    company_access = await user_repo.list_company_access_with_names(user_id)
    if not any(row["company_id"] == ctx.company_id for row in company_access):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    roles = await role_repo.list_for_user_in_company(user_id, ctx.company_id)
    return UserDetailOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_2fa_enabled=user.is_2fa_enabled,
        roles=roles,
        company_access=[CompanyAccessRow(**row) for row in company_access],
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("user.create")),
    user_repo: UserRepository = Depends(get_user_repo),
    role_repo: RoleRepository = Depends(get_role_repo),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    user_service = UserManagementService(user_repo, role_repo, company_repo)
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


@router.delete("/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role(
    user_id: UUID,
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("user.manage_roles")),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    """Symmetric counterpart to `POST /users/{user_id}/roles` — a role
    checkbox in the Users UI that could only ever be checked, never
    unchecked, would be a half-built screen."""
    await role_repo.remove_from_user(user_id=user_id, role_id=role_id)
    await AuditLogRepository(db).record(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        target_table="user_role",
        target_id=user_id,
        field_name="role_id",
        old_value=str(role_id),
        new_value=None,
    )
    await db.commit()


@router.post("/users/{user_id}/company-access", status_code=status.HTTP_204_NO_CONTENT)
async def grant_company_access(
    user_id: UUID,
    payload: CompanyAccessGrantRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("user.manage_roles")),
    user_repo: UserRepository = Depends(get_user_repo),
    role_repo: RoleRepository = Depends(get_role_repo),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """UI/UX Foundation milestone: exposes the already-existing, already-used
    UserRepository.grant_company_access for an existing user, so a genuine
    multi-company login can be built and tested via the real API — no such
    endpoint existed before (create_user only ever grants access to the one
    company being created for). Scoped to the caller's own tenant/company
    catalog; does not add any broader role-management surface."""
    user_service = UserManagementService(user_repo, role_repo, company_repo)
    try:
        # user_company_access carries company_isolation RLS keyed off the
        # row's own company_id — get_auth_context() only set the session to
        # the caller's *active* company, which is the wrong context when
        # granting access to a *different* company (found live while
        # verifying the two-company acceptance scenario: real 403 from
        # Postgres, not a bug in the grant logic itself).
        await set_company_context(db, payload.company_id)
        await user_service.grant_company_access(
            tenant_id=ctx.tenant_id,
            user_id=user_id,
            company_id=payload.company_id,
            branch_id=payload.branch_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    # Restore the caller's own active-company context before writing the
    # audit log entry, which is recorded against ctx.company_id, not the
    # company access was just granted to.
    await set_company_context(db, ctx.company_id)
    await AuditLogRepository(db).record(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        target_table="user_company_access",
        target_id=user_id,
        field_name="company_id",
        old_value=None,
        new_value=str(payload.company_id),
    )
    await db.commit()


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(
    ctx: AuthContext = Depends(require_permission("role.manage")),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    """Settings Architecture Foundation milestone — the fixed, global
    permission catalog a Security settings screen renders as a checkbox
    matrix. Not company-scoped (Permission has no company_id, Phase 7)."""
    return await role_repo.list_all_permissions()


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    ctx: AuthContext = Depends(require_permission("role.manage")),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    return await role_repo.list_by_company(ctx.company_id)


@router.get("/roles/{role_id}", response_model=RoleDetailOut)
async def get_role(
    role_id: UUID,
    ctx: AuthContext = Depends(require_permission("role.manage")),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    role = await role_repo.get_by_id(ctx.company_id, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    permission_codes = await role_repo.get_role_permission_codes(role.id)
    return RoleDetailOut(id=role.id, name=role.name, is_system=role.is_system, permission_codes=sorted(permission_codes))


@router.post("/roles", response_model=RoleDetailOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("role.manage")),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    """Creates an empty custom role (no permissions yet — granted via
    PUT /roles/{id}/permissions right after, same as the checkbox-matrix +
    Save flow the Security screen uses for editing any other role)."""
    import uuid as _uuid

    from src.modules.identity.infrastructure.models import Role

    role = Role(id=_uuid.uuid4(), company_id=ctx.company_id, name=payload.name, is_system=False)
    await role_repo.add(role)
    await AuditLogRepository(db).record(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        target_table="role",
        target_id=role.id,
        field_name="name",
        old_value=None,
        new_value=role.name,
    )
    await db.commit()
    return RoleDetailOut(id=role.id, name=role.name, is_system=role.is_system, permission_codes=[])


@router.patch("/roles/{role_id}", response_model=RoleDetailOut)
async def rename_role(
    role_id: UUID,
    payload: RoleRenameRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("role.manage")),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    """P0-6 (3-Day Brief) — RBAC completion: renaming a role (fixing a
    typo, or relabeling one to match how the Owner's team actually talks
    about it) previously had no API at all, only direct DB access."""
    role = await role_repo.get_by_id(ctx.company_id, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if role.is_system:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "System roles cannot be renamed")

    old_name = role.name
    await role_repo.rename(role, payload.name)
    if old_name != payload.name:
        await AuditLogRepository(db).record(
            tenant_id=ctx.tenant_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            target_table="role",
            target_id=role.id,
            field_name="name",
            old_value=old_name,
            new_value=payload.name,
        )
    permission_codes = await role_repo.get_role_permission_codes(role.id)
    await db.commit()
    return RoleDetailOut(id=role.id, name=role.name, is_system=role.is_system, permission_codes=sorted(permission_codes))


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("role.manage")),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    """P0-6 (3-Day Brief) — RBAC completion: a role that's obsolete or was
    created by mistake previously had no way to be removed short of direct
    DB access. Mirrors the Chart of Accounts' own delete_account guard
    (P0-4) — rejected if the record still has real dependents (here: users
    still holding it) rather than silently orphaning their access."""
    role = await role_repo.get_by_id(ctx.company_id, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if role.is_system:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "System roles cannot be deleted")
    assigned = await role_repo.count_user_assignments(role.id)
    if assigned > 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Cannot delete — {assigned} user(s) still hold this role; remove them from it first",
        )

    await AuditLogRepository(db).record(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        target_table="role",
        target_id=role.id,
        field_name="deleted_at",
        old_value=None,
        new_value="now",
    )
    await role_repo.delete(role)
    await db.commit()


@router.put("/roles/{role_id}/permissions", response_model=RoleDetailOut)
async def update_role_permissions(
    role_id: UUID,
    payload: RolePermissionsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("role.manage")),
    role_repo: RoleRepository = Depends(get_role_repo),
):
    """The fix for a real, previously-documented operational gap: until now
    a role's permissions were fixed at creation time (bootstrap or
    company-create), with no way to grant an already-existing role a
    permission added by a later product change — hit twice during the
    Entity Media Foundation milestone, which needed a freshly-bootstrapped
    company each time just to test a new permission."""
    role = await role_repo.get_by_id(ctx.company_id, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    if role.is_system:
        # P0-6 (3-Day Brief): the seeded "Admin" role is now the one
        # guaranteed way back into a company's own access model — a test
        # already on record (test_settings_roles.py) proves that stripping
        # role.manage off the last role that grants it locks a company out
        # of ever granting a permission again, with no in-product recovery.
        # Making the system role immutable closes that off entirely:
        # Admin can never be edited down, so there's always a way back in.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "System role permissions cannot be edited")

    all_permissions = await role_repo.list_all_permissions()
    by_code = {p.code: p.id for p in all_permissions}
    unknown = [code for code in payload.permission_codes if code not in by_code]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown permission code(s): {', '.join(unknown)}")

    old_codes = await role_repo.get_role_permission_codes(role.id)
    new_codes = set(payload.permission_codes)
    permission_ids = [by_code[code] for code in new_codes]
    await role_repo.set_permissions(role.id, permission_ids)

    if old_codes != new_codes:
        await AuditLogRepository(db).record(
            tenant_id=ctx.tenant_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            target_table="role",
            target_id=role.id,
            field_name="permissions",
            old_value=", ".join(sorted(old_codes)),
            new_value=", ".join(sorted(new_codes)),
        )

    await db.commit()
    return RoleDetailOut(id=role.id, name=role.name, is_system=role.is_system, permission_codes=sorted(new_codes))


@router.get("/partners", response_model=list[PartnerOut])
async def list_partners(
    customers_only: bool = False,
    vendors_only: bool = False,
    employees_only: bool = False,
    parent_partner_id: UUID | None = None,
    include_archived: bool = False,
    search: str | None = None,
    ctx: AuthContext = Depends(require_permission("partner.view")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    """Unfiltered (no role flag set) = the Address Book master view;
    customers_only/vendors_only/employees_only turn this into the Customers/
    Vendors/Employees screens — all filtered views over the same table, per
    the Unified Address Book bundle. parent_partner_id lists a single
    company's Contacts (child partners)."""
    return await partner_repo.list_by_company(
        ctx.company_id,
        customers_only=customers_only,
        vendors_only=vendors_only,
        employees_only=employees_only,
        parent_partner_id=parent_partner_id,
        search=search,
        include_archived=include_archived,
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
    # include_archived=True so an archived partner's profile (and its
    # Restore action) stays reachable — every other call site keeps the
    # default (active-only), so this has no effect outside this one route.
    partner = await partner_repo.get_by_id(partner_id, include_archived=True)
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
            is_company=payload.is_company,
            parent_partner_id=payload.parent_partner_id,
            is_customer=payload.is_customer,
            is_vendor=payload.is_vendor,
            is_employee=payload.is_employee,
            job_title=payload.job_title,
            is_primary_contact=payload.is_primary_contact,
            phone=payload.phone,
            mobile=payload.mobile,
            email=payload.email,
            website=payload.website,
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
            is_company=payload.is_company,
            is_customer=payload.is_customer,
            is_vendor=payload.is_vendor,
            is_employee=payload.is_employee,
            job_title=payload.job_title,
            is_primary_contact=payload.is_primary_contact,
            phone=payload.phone,
            mobile=payload.mobile,
            email=payload.email,
            website=payload.website,
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


@router.post("/partners/{partner_id}/archive", response_model=PartnerOut)
async def archive_partner(
    partner_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("partner.update")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    service = PartnerService(partner_repo)
    try:
        partner = await service.archive_partner(company_id=ctx.company_id, partner_id=partner_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    await db.commit()
    return partner


@router.post("/partners/{partner_id}/restore", response_model=PartnerOut)
async def restore_partner(
    partner_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("partner.update")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    service = PartnerService(partner_repo)
    try:
        partner = await service.restore_partner(company_id=ctx.company_id, partner_id=partner_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    await db.commit()
    return partner


@router.get("/partners/{partner_id}/addresses", response_model=list[PartnerAddressOut])
async def list_partner_addresses(
    partner_id: UUID,
    ctx: AuthContext = Depends(require_permission("partner.view")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
    address_repo: PartnerAddressRepository = Depends(get_partner_address_repo),
):
    partner = await partner_repo.get_by_id(partner_id, include_archived=True)
    if partner is None or partner.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
    return await address_repo.list_by_partner(ctx.company_id, partner_id)


@router.post("/partners/{partner_id}/addresses", response_model=PartnerAddressOut, status_code=status.HTTP_201_CREATED)
async def create_partner_address(
    partner_id: UUID,
    payload: PartnerAddressCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("partner.update")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
    address_repo: PartnerAddressRepository = Depends(get_partner_address_repo),
):
    service = PartnerService(partner_repo, address_repo)
    try:
        address = await service.add_address(
            company_id=ctx.company_id,
            partner_id=partner_id,
            type=payload.type,
            is_default=payload.is_default,
            street=payload.street,
            city=payload.city,
            region=payload.region,
            postal_code=payload.postal_code,
            country_code=payload.country_code,
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    await db.commit()
    return address


@router.patch("/partners/{partner_id}/addresses/{address_id}", response_model=PartnerAddressOut)
async def update_partner_address(
    partner_id: UUID,
    address_id: UUID,
    payload: PartnerAddressUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("partner.update")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
    address_repo: PartnerAddressRepository = Depends(get_partner_address_repo),
):
    service = PartnerService(partner_repo, address_repo)
    try:
        address = await service.update_address(
            company_id=ctx.company_id,
            partner_id=partner_id,
            address_id=address_id,
            type=payload.type,
            is_default=payload.is_default,
            street=payload.street,
            city=payload.city,
            region=payload.region,
            postal_code=payload.postal_code,
            country_code=payload.country_code,
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    await db.commit()
    return address


@router.delete("/partners/{partner_id}/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner_address(
    partner_id: UUID,
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("partner.update")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
    address_repo: PartnerAddressRepository = Depends(get_partner_address_repo),
):
    service = PartnerService(partner_repo, address_repo)
    try:
        await service.delete_address(company_id=ctx.company_id, partner_id=partner_id, address_id=address_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    await db.commit()


@router.post("/partners/{partner_id}/image", response_model=PartnerOut)
async def upload_partner_image(
    partner_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("partner.update")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    """Entity Media Foundation. Same explicit company_id check as
    get_partner()/update_partner() above — partner_repo isn't itself
    company-scoped."""
    partner = await partner_repo.get_by_id(partner_id)
    if partner is None or partner.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")

    try:
        relative_path = await save_entity_image(file, entity_type="partner", entity_id=str(partner.id))
    except InvalidImageError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    old_path = partner.image_path
    partner.image_path = relative_path
    # See the comment on the equivalent company-logo endpoint above for why
    # there's deliberately no db.refresh() here.
    await db.commit()
    delete_entity_image(old_path)
    return partner


@router.delete("/partners/{partner_id}/image", response_model=PartnerOut)
async def delete_partner_image(
    partner_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("partner.update")),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
):
    partner = await partner_repo.get_by_id(partner_id)
    if partner is None or partner.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")

    old_path = partner.image_path
    partner.image_path = None
    # See the comment on the equivalent company-logo endpoint above for why
    # there's deliberately no db.refresh() here.
    await db.commit()
    delete_entity_image(old_path)
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
            price_high=payload.price_high,
            price_low=payload.price_low,
            default_tax_rate_id=payload.default_tax_rate_id,
            reorder_point=payload.reorder_point,
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
            price_high=payload.price_high,
            price_low=payload.price_low,
            default_tax_rate_id=payload.default_tax_rate_id,
            reorder_point=payload.reorder_point,
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return product


@router.post("/products/{product_id}/image", response_model=ProductOut)
async def upload_product_image(
    product_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("product.update")),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    """Entity Media Foundation. Same explicit company_id check as
    get_product()/update_product() above."""
    product = await product_repo.get_by_id(product_id)
    if product is None or product.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    try:
        relative_path = await save_entity_image(file, entity_type="product", entity_id=str(product.id))
    except InvalidImageError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    old_path = product.image_path
    product.image_path = relative_path
    # See the comment on the equivalent company-logo endpoint above for why
    # there's deliberately no db.refresh() here.
    await db.commit()
    delete_entity_image(old_path)
    return product


@router.delete("/products/{product_id}/image", response_model=ProductOut)
async def delete_product_image(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("product.update")),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    product = await product_repo.get_by_id(product_id)
    if product is None or product.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    old_path = product.image_path
    product.image_path = None
    # See the comment on the equivalent company-logo endpoint above for why
    # there's deliberately no db.refresh() here.
    await db.commit()
    delete_entity_image(old_path)
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
