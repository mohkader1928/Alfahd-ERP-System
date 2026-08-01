"""Application services (use-case orchestration), Phase 8 §2.

Each public method here = one use case from Phase 4 (UC-CORE-*). A method
starts no I/O beyond what's needed for that single use case, and the caller
(API route) is responsible for committing the Unit of Work.
"""

import uuid
from decimal import Decimal
from uuid import UUID

from src.modules.identity.domain.entities import InactiveUserError
from src.modules.identity.infrastructure.master_data_models import Partner, Product
from src.modules.identity.infrastructure.models import (
    AppUser,
    Branch,
    Company,
    Role,
    Tenant,
)
from src.modules.identity.infrastructure.repositories import (
    BranchRepository,
    CompanyRepository,
    CurrencyRepository,
    PartnerRepository,
    ProductRepository,
    RoleRepository,
    UserRepository,
)
from src.shared.security.jwt import create_access_token, create_refresh_token
from src.shared.security.password import hash_password, validate_password_policy, verify_password
from src.shared.security.totp import verify_totp_code


class AuthenticationError(Exception):
    pass


class TwoFactorRequiredError(Exception):
    """Raised to signal the client must submit a TOTP code to complete login."""


class CompanyRegistrationService:
    """UC-CORE-02 — Register Company & Branch."""

    def __init__(self, company_repo: CompanyRepository, branch_repo: BranchRepository, currency_repo: CurrencyRepository):
        self.company_repo = company_repo
        self.branch_repo = branch_repo
        self.currency_repo = currency_repo

    async def register_company(
        self,
        *,
        tenant_id: UUID,
        legal_name: str,
        legal_name_ar: str,
        vat_number: str,
        base_currency_code: str,
        valuation_method: str,
        main_branch_name: str,
        main_branch_name_ar: str,
    ) -> tuple[Company, Branch]:
        currency = await self.currency_repo.get_by_code(base_currency_code)
        if currency is None:
            raise ValueError(f"Unknown currency code: {base_currency_code}")

        company = Company(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            legal_name=legal_name,
            legal_name_ar=legal_name_ar,
            vat_number=vat_number,
            base_currency_id=currency.id,
            valuation_method=valuation_method,
        )
        await self.company_repo.add(company)

        branch = Branch(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            company_id=company.id,
            name=main_branch_name,
            name_ar=main_branch_name_ar,
            is_main=True,
        )
        await self.branch_repo.add(branch)

        return company, branch


class UserManagementService:
    """UC-CORE-03 — user creation and role assignment."""

    def __init__(self, user_repo: UserRepository, role_repo: RoleRepository):
        self.user_repo = user_repo
        self.role_repo = role_repo

    async def create_user(
        self,
        *,
        tenant_id: UUID,
        email: str,
        full_name: str,
        plain_password: str,
        company_id: UUID,
        branch_id: UUID | None = None,
    ) -> AppUser:
        validate_password_policy(plain_password)
        existing = await self.user_repo.get_by_email(email)
        if existing is not None:
            raise ValueError("A user with this email already exists")

        user = AppUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(plain_password),
        )
        await self.user_repo.add(user)
        await self.user_repo.grant_company_access(user.id, company_id, branch_id)
        return user

    async def create_role(self, *, company_id: UUID, name: str, permission_codes: list[str]) -> Role:
        role = Role(id=uuid.uuid4(), company_id=company_id, name=name)
        await self.role_repo.add(role)
        for code in permission_codes:
            permission = await self.role_repo.get_permission_by_code(code)
            if permission is None:
                raise ValueError(f"Unknown permission code: {code}")
            await self.role_repo.grant_permission(role.id, permission.id)
        return role

    async def assign_role(self, *, user_id: UUID, role_id: UUID) -> None:
        await self.role_repo.assign_to_user(user_id, role_id)


class AuthenticationService:
    """UC-CORE-01 — Login with optional 2FA."""

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def authenticate_step1(self, *, email: str, plain_password: str) -> AppUser:
        user = await self.user_repo.get_by_email(email)
        if user is None or not verify_password(plain_password, user.password_hash):
            raise AuthenticationError("Invalid email or password")

        try:
            _assert_can_login(user)
        except InactiveUserError as e:
            raise AuthenticationError(str(e)) from e

        if user.is_2fa_enabled:
            raise TwoFactorRequiredError()

        return user

    async def authenticate_step2_totp(self, *, email: str, plain_password: str, totp_code: str) -> AppUser:
        user = await self.user_repo.get_by_email(email)
        if user is None or not verify_password(plain_password, user.password_hash):
            raise AuthenticationError("Invalid email or password")
        if not user.is_2fa_enabled or not user.totp_secret:
            raise AuthenticationError("2FA is not enabled for this user")
        if not verify_totp_code(user.totp_secret, totp_code):
            raise AuthenticationError("Invalid 2FA code")
        return user

    async def issue_tokens(self, user: AppUser) -> dict[str, str]:
        access_entries = await self.user_repo.list_authorized_companies(user.id)
        authorized_companies = [
            f"{a.company_id}:{a.branch_id}" if a.branch_id else str(a.company_id) for a in access_entries
        ]
        access_token = create_access_token(
            user_id=user.id, tenant_id=user.tenant_id, authorized_companies=authorized_companies
        )
        refresh_token = create_refresh_token(user_id=user.id)
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


def _assert_can_login(user: AppUser) -> None:
    if not user.is_active:
        raise InactiveUserError("This user account has been deactivated")


class TenantProvisioningService:
    """Bootstraps a new Tenant (top-level owner) — precondition for UC-CORE-02."""

    def __init__(self, session):
        self.session = session

    async def create_tenant(self, legal_name: str) -> Tenant:
        tenant = Tenant(id=uuid.uuid4(), legal_name=legal_name)
        self.session.add(tenant)
        await self.session.flush()
        return tenant


class PartnerService:
    """FR-CORE-042 — unified customer/vendor contact, consumed by Sales (M2)
    and Purchasing (M4)."""

    def __init__(self, partner_repo: PartnerRepository):
        self.partner_repo = partner_repo

    async def create_partner(
        self,
        *,
        tenant_id: UUID,
        company_id: UUID,
        name: str,
        name_ar: str | None = None,
        is_customer: bool = False,
        is_vendor: bool = False,
        vat_number: str | None = None,
        cr_number: str | None = None,
    ) -> Partner:
        if not is_customer and not is_vendor:
            raise ValueError("A partner must be a customer, a vendor, or both")
        partner = Partner(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            company_id=company_id,
            name=name,
            name_ar=name_ar,
            is_customer=is_customer,
            is_vendor=is_vendor,
            vat_number=vat_number,
            cr_number=cr_number,
        )
        return await self.partner_repo.add(partner)


class ProductService:
    """FR-CORE-045 — item/service master, consumed by Sales/Purchasing/Inventory."""

    def __init__(self, product_repo: ProductRepository):
        self.product_repo = product_repo

    async def create_product(
        self,
        *,
        tenant_id: UUID,
        company_id: UUID,
        sku: str,
        name: str,
        name_ar: str | None = None,
        is_stockable: bool = True,
        sales_price: Decimal = Decimal("0"),
        cost_price: Decimal = Decimal("0"),
        default_tax_rate_id: UUID | None = None,
    ) -> Product:
        existing = await self.product_repo.get_by_sku(company_id, sku)
        if existing is not None:
            raise ValueError(f"Product SKU already exists: {sku}")
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            company_id=company_id,
            sku=sku,
            name=name,
            name_ar=name_ar,
            is_stockable=is_stockable,
            sales_price=sales_price,
            cost_price=cost_price,
            default_tax_rate_id=default_tax_rate_id,
        )
        return await self.product_repo.add(product)
