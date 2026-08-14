"""Application services (use-case orchestration), Phase 8 §2.

Each public method here = one use case from Phase 4 (UC-CORE-*). A method
starts no I/O beyond what's needed for that single use case, and the caller
(API route) is responsible for committing the Unit of Work.
"""

import hashlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.modules.identity.domain.entities import InactiveUserError
from src.modules.identity.infrastructure.master_data_models import (
    Partner,
    PartnerAddress,
    Product,
    ProductCategory,
    UnitOfMeasure,
)
from src.modules.identity.infrastructure.models import (
    AppUser,
    Branch,
    Company,
    PasswordResetToken,
    Role,
    Tenant,
)
from src.modules.identity.infrastructure.repositories import (
    BranchRepository,
    CompanyRepository,
    CurrencyRepository,
    PartnerAddressRepository,
    PartnerRepository,
    PasswordResetTokenRepository,
    ProductCategoryRepository,
    ProductRepository,
    RoleRepository,
    UnitOfMeasureRepository,
    UserRepository,
)
from src.shared.email.mailer import EmailNotConfiguredError
from src.shared.email.mailer import send_email as default_send_email
from src.shared.infrastructure.db.session import set_tenant_context
from src.shared.security.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.shared.security.password import hash_password, validate_password_policy, verify_password
from src.shared.security.totp import generate_totp_secret, get_provisioning_uri, verify_totp_code


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

    def __init__(self, user_repo: UserRepository, role_repo: RoleRepository, company_repo: CompanyRepository):
        self.user_repo = user_repo
        self.role_repo = role_repo
        self.company_repo = company_repo

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

    async def start_2fa_enrollment(self, *, user_id: UUID, email: str) -> tuple[str, str]:
        """P0-3 (Phase-One audit closure) — FR-CORE-011's verification half
        (`authenticate_step2_totp`) already existed and was already
        correctly tested; only this half (getting a real, verified secret
        onto the user's row in the first place) was missing. Generates a
        fresh pending secret and returns its provisioning URI (the
        frontend renders this into a real QR via the already-installed,
        previously-unused `react-qr-code`) — 2FA is NOT enabled by this
        call alone; only `verify_2fa_enrollment` flips that flag, and only
        after proving the user actually captured the secret in a real
        authenticator app. Blocks re-enrollment while already enabled:
        silently rotating the secret out from under an active device would
        strand the user's existing authenticator mid-session for no
        benefit this task requires (there is no disable-2FA flow yet to
        recover from that)."""
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        if user.is_2fa_enabled:
            raise ValueError("2FA is already enabled for this account")
        secret = generate_totp_secret()
        user.totp_secret = secret
        return secret, get_provisioning_uri(secret, email)

    async def verify_2fa_enrollment(self, *, user_id: UUID, totp_code: str) -> AppUser:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        if user.is_2fa_enabled:
            raise ValueError("2FA is already enabled for this account")
        if not user.totp_secret:
            raise ValueError("No 2FA enrollment in progress — start enrollment first")
        if not verify_totp_code(user.totp_secret, totp_code):
            raise ValueError("Invalid verification code")
        user.is_2fa_enabled = True
        return user

    async def create_role(
        self, *, company_id: UUID, name: str, permission_codes: list[str], is_system: bool = False
    ) -> Role:
        role = Role(id=uuid.uuid4(), company_id=company_id, name=name, is_system=is_system)
        await self.role_repo.add(role)
        for code in permission_codes:
            permission = await self.role_repo.get_permission_by_code(code)
            if permission is None:
                raise ValueError(f"Unknown permission code: {code}")
            await self.role_repo.grant_permission(role.id, permission.id)
        return role

    async def seed_default_role_templates(self, *, company_id: UUID) -> list[Role]:
        """P0-6 (3-Day Brief) — RBAC completion. Every company previously
        started with exactly one role ("Admin", holding the entire
        permission catalog) and zero others — real separation of duties
        was 100% manual, built from a blank checkbox matrix in Settings.
        These four templates give a new company a real out-of-the-box
        access model on day one; they're ordinary (non-system) roles, so
        the Owner can still freely edit or delete them to fit their own
        org — unlike Admin (see `is_system` on create_role's caller),
        nothing here is locked.

        "Read-Only Viewer" is deliberately *derived* from the catalog
        (every `screen`-scope code) rather than hand-listed like the
        other three, so it never drifts out of sync as new view
        permissions are added — a hand-maintained list would silently
        miss every future report/screen permission unless someone
        remembered to update it here too.
        """
        from src.shared.infrastructure.db.seed import PERMISSION_CATALOG

        templates: list[tuple[str, list[str]]] = [
            (
                "Accountant",
                [
                    "accounting.chart_of_accounts.view",
                    "accounting.chart_of_accounts.manage",
                    "accounting.journal_entry.view",
                    "accounting.journal_entry.create",
                    "accounting.journal_entry.post",
                    "accounting.journal_entry.reverse",
                    "accounting.journal_entry.cancel",
                    "accounting.fiscal_period.manage",
                    "accounting.reports.trial_balance.view",
                    "accounting.reports.general_ledger.view",
                    "accounting.reports.income_statement.view",
                    "accounting.reports.balance_sheet.view",
                    "accounting.tax_rate.view",
                    "payment.view",
                    "payment.create",
                    "payment.subledger.view",
                    "payment.aging.view",
                    "fixed_assets.view",
                    "fixed_assets.create",
                    "fixed_assets.depreciation.run",
                    "fixed_assets.dispose",
                    "fixed_assets.category.manage",
                    "reporting.vat.view",
                    "reporting.dashboard.view",
                    "reporting.export",
                    "partner.view",
                    "product.view",
                    "attachment.view",
                    "attachment.manage",
                    "search.use",
                ],
            ),
            (
                "Sales",
                [
                    "sales.quotation.create",
                    "sales.quotation.update",
                    "sales.quotation.confirm",
                    "sales.quotation.send_email",
                    "sales.order.view",
                    "sales.invoice.create",
                    "sales.invoice.credit_note",
                    "sales.invoice.send_email",
                    "accounting.tax_rate.view",
                    "inventory.warehouse.view",
                    "inventory.stock.view",
                    "partner.view",
                    "partner.create",
                    "partner.update",
                    "product.view",
                    "payment.view",
                    "payment.create",
                    "reporting.sales.view",
                    "reporting.dashboard.view",
                    "attachment.view",
                    "attachment.manage",
                    "search.use",
                ],
            ),
            (
                "Purchasing & Warehouse",
                [
                    "purchasing.order.create",
                    "purchasing.order.update",
                    "purchasing.order.confirm",
                    "purchasing.order.approve",
                    "purchasing.order.view",
                    "purchasing.order.short_close",
                    "purchasing.order.reopen",
                    "purchasing.goods_receipt.create",
                    "purchasing.vendor_bill.create",
                    "purchasing.vendor_bill.update",
                    "purchasing.vendor_bill.view",
                    "purchasing.vendor_bill.approve",
                    "purchasing.vendor_bill.debit_note",
                    "accounting.tax_rate.view",
                    "inventory.warehouse.manage",
                    "inventory.warehouse.view",
                    "inventory.stock.receive",
                    "inventory.stock.view",
                    "inventory.transfer.create",
                    "inventory.cycle_count.manage",
                    "partner.view",
                    "product.view",
                    "product_category.view",
                    "uom.view",
                    "payment.view",
                    "payment.create",
                    "reporting.purchasing.view",
                    "reporting.inventory_valuation.view",
                    "reporting.dashboard.view",
                    "attachment.view",
                    "attachment.manage",
                    "search.use",
                ],
            ),
            (
                "Read-Only Viewer",
                [code for code, scope in PERMISSION_CATALOG if scope == "screen"],
            ),
        ]
        return [
            await self.create_role(company_id=company_id, name=name, permission_codes=codes, is_system=False)
            for name, codes in templates
        ]

    async def assign_role(self, *, user_id: UUID, role_id: UUID) -> None:
        await self.role_repo.assign_to_user(user_id, role_id)

    async def grant_company_access(
        self, *, tenant_id: UUID, user_id: UUID, company_id: UUID, branch_id: UUID | None = None
    ) -> None:
        """UI/UX Foundation milestone — lets an already-existing user be
        authorized for an additional company, so a real multi-company login
        can be tested. Reuses UserRepository.grant_company_access exactly as
        create_user's own bootstrap path already does; this only exposes it
        for a user who already exists, instead of only at creation time.
        """
        user = await self.user_repo.get_by_id(user_id)
        if user is None or user.tenant_id != tenant_id:
            raise ValueError("User not found")

        company = await self.company_repo.get_by_id(company_id)
        if company is None or company.tenant_id != tenant_id:
            raise ValueError("Company not found")

        existing = await self.user_repo.list_authorized_companies(user_id)
        if any(a.company_id == company_id and a.branch_id == branch_id for a in existing):
            raise ValueError("User already has access to this company")

        await self.user_repo.grant_company_access(user_id, company_id, branch_id)


class AuthenticationService:
    """UC-CORE-01 — Login with optional 2FA."""

    # P0-B (Phase-One closure): the audit found no brute-force protection at
    # all on the password/2FA guess surface. A fixed, auto-expiring lockout
    # (never permanent) reusing the same failed_login_count/locked_until
    # columns added alongside P0-A (migration a8b9c0d1e2f3) for both.
    MAX_FAILED_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def authenticate_step1(self, *, email: str, plain_password: str) -> AppUser:
        user = await self.user_repo.get_by_email(email)
        if user is None:
            raise AuthenticationError("Invalid email or password")
        # Same rationale as PasswordResetService.confirm_reset: this write
        # (failed_login_count/locked_until) happens before any tenant
        # context normally exists, so tenant_isolation on app_user needs it
        # set explicitly once the user (and their tenant) is resolved.
        await set_tenant_context(self.user_repo.session, user.tenant_id)
        self._assert_not_locked(user)

        if not verify_password(plain_password, user.password_hash):
            self._register_failed_attempt(user)
            raise AuthenticationError("Invalid email or password")
        self._register_successful_attempt(user)

        try:
            _assert_can_login(user)
        except InactiveUserError as e:
            raise AuthenticationError(str(e)) from e

        if user.is_2fa_enabled:
            raise TwoFactorRequiredError()

        return user

    async def authenticate_step2_totp(self, *, email: str, plain_password: str, totp_code: str) -> AppUser:
        user = await self.user_repo.get_by_email(email)
        if user is None:
            raise AuthenticationError("Invalid email or password")
        await set_tenant_context(self.user_repo.session, user.tenant_id)
        self._assert_not_locked(user)

        if not verify_password(plain_password, user.password_hash):
            self._register_failed_attempt(user)
            raise AuthenticationError("Invalid email or password")
        if not user.is_2fa_enabled or not user.totp_secret:
            raise AuthenticationError("2FA is not enabled for this user")
        if not verify_totp_code(user.totp_secret, totp_code):
            self._register_failed_attempt(user)
            raise AuthenticationError("Invalid 2FA code")

        self._register_successful_attempt(user)
        return user

    def _assert_not_locked(self, user: AppUser) -> None:
        if user.locked_until is not None and user.locked_until > datetime.now(UTC).replace(tzinfo=None):
            raise AuthenticationError(
                "This account is temporarily locked due to too many failed login attempts. "
                "Try again later, or reset your password to regain access immediately."
            )

    def _register_failed_attempt(self, user: AppUser) -> None:
        user.failed_login_count += 1
        if user.failed_login_count >= self.MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                minutes=self.LOCKOUT_DURATION_MINUTES
            )

    def _register_successful_attempt(self, user: AppUser) -> None:
        user.failed_login_count = 0
        user.locked_until = None

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

    async def refresh_tokens(self, *, refresh_token: str) -> dict[str, str]:
        """Owner-reported bug: the access token (30 min) had no renewal path
        at all — the refresh token was minted at login and then never used
        for anything, so an idle session died hard and the only recovery
        was a full manual logout/login. Mirrors issue_tokens()'s own shape:
        validate the refresh token, re-fetch the user (so a deactivated
        account can't renew), and mint a brand new pair (rotating the
        refresh token too, not just the access token)."""
        try:
            payload = decode_token(refresh_token)
        except TokenError as e:
            raise AuthenticationError("Invalid or expired refresh token") from e
        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid or expired refresh token")

        user = await self.user_repo.get_by_id(UUID(payload["sub"]))
        if user is None:
            raise AuthenticationError("Invalid or expired refresh token")
        try:
            _assert_can_login(user)
        except InactiveUserError as e:
            raise AuthenticationError(str(e)) from e

        return await self.issue_tokens(user)


def _assert_can_login(user: AppUser) -> None:
    if not user.is_active:
        raise InactiveUserError("This user account has been deactivated")


class PasswordResetService:
    """P0-A (Phase-One closure) — the audit found no password-recovery path
    anywhere in the codebase. Reuses the existing password policy/hashing
    (src.shared.security.password) and mailer (src.shared.email.mailer)
    as-is; does not touch authenticate_step1/2 or token issuance."""

    RESET_TOKEN_TTL_MINUTES = 30

    def __init__(self, user_repo: UserRepository, reset_token_repo: PasswordResetTokenRepository):
        self.user_repo = user_repo
        self.reset_token_repo = reset_token_repo

    async def request_reset(
        self,
        *,
        email: str,
        mailer: Callable[..., Awaitable[None]] = default_send_email,
    ) -> None:
        """Anti-enumeration: always returns normally whether the email
        exists, belongs to a deactivated user, or SMTP isn't configured —
        the client can't distinguish any of those cases from a real send."""
        user = await self.user_repo.get_by_email(email)
        if user is None or not user.is_active:
            return

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        await self.reset_token_repo.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC).replace(tzinfo=None)
                + timedelta(minutes=self.RESET_TOKEN_TTL_MINUTES),
            )
        )

        subject = "Password Reset Request"
        body = (
            f"Dear {user.full_name},\n\n"
            "A password reset was requested for your account. Use the code below to set a "
            f"new password. This code expires in {self.RESET_TOKEN_TTL_MINUTES} minutes and can "
            "only be used once.\n\n"
            f"{raw_token}\n\n"
            "If you did not request this, you can safely ignore this email — your password "
            "will not be changed."
        )
        try:
            await mailer(to=user.email, subject=subject, body=body)
        except EmailNotConfiguredError:
            pass

    async def confirm_reset(self, *, raw_token: str, new_password: str) -> AppUser:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        token = await self.reset_token_repo.get_by_hash(token_hash)
        now = datetime.now(UTC).replace(tzinfo=None)
        if token is None or token.used_at is not None or token.expires_at < now:
            raise AuthenticationError("Invalid or expired reset token")

        user = await self.user_repo.get_by_id(token.user_id)
        if user is None:
            raise AuthenticationError("Invalid or expired reset token")
        try:
            _assert_can_login(user)
        except InactiveUserError as e:
            raise AuthenticationError(str(e)) from e

        # The reset token (looked up pre-tenant, same as the login-lookup
        # RLS escape hatch) is what establishes which tenant this write
        # belongs to — tenant_isolation on app_user otherwise blocks the
        # UPDATE below with no `app.current_tenant_id` set.
        await set_tenant_context(self.user_repo.session, user.tenant_id)

        validate_password_policy(new_password)
        user.password_hash = hash_password(new_password)
        # A successful reset is also this system's account-recovery path
        # for P0-B's login lockout — clearing it here means a locked-out
        # user is never permanently stuck.
        user.failed_login_count = 0
        user.locked_until = None
        token.used_at = now
        return user


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
    """FR-CORE-042 — the one master entity for company/individual,
    Customer/Vendor/Employee, and Contact Person (Unified Address Book
    bundle). Consumed by Sales (M2), Purchasing (M4), and the Address Book/
    Customers/Vendors/Employees screens, which are all filtered views over
    this same table.

    Validation deliberately no longer requires is_customer/is_vendor: a
    Partner can be a pure Contact Person (a child of a company, via
    parent_partner_id, with no role flags at all) or a company/individual
    created before any role is decided — both are legitimate states now
    that Employee and Contact are first-class alongside Customer/Vendor.
    """

    def __init__(self, partner_repo: PartnerRepository, address_repo: PartnerAddressRepository | None = None):
        self.partner_repo = partner_repo
        self.address_repo = address_repo

    async def _validate_parent(self, *, company_id: UUID, parent_partner_id: UUID | None, self_id: UUID | None) -> None:
        if parent_partner_id is None:
            return
        if self_id is not None and parent_partner_id == self_id:
            raise ValueError("A partner cannot be its own parent")
        parent = await self.partner_repo.get_by_id(parent_partner_id)
        if parent is None or parent.company_id != company_id:
            raise ValueError("Parent partner not found")

    async def create_partner(
        self,
        *,
        tenant_id: UUID,
        company_id: UUID,
        name: str,
        name_ar: str | None = None,
        is_company: bool = True,
        parent_partner_id: UUID | None = None,
        is_customer: bool = False,
        is_vendor: bool = False,
        is_employee: bool = False,
        job_title: str | None = None,
        is_primary_contact: bool = False,
        phone: str | None = None,
        mobile: str | None = None,
        email: str | None = None,
        website: str | None = None,
        vat_number: str | None = None,
        cr_number: str | None = None,
        payment_terms: str | None = None,
        address: dict | None = None,
    ) -> Partner:
        await self._validate_parent(company_id=company_id, parent_partner_id=parent_partner_id, self_id=None)
        # Owner directive: partner_code is always system-assigned, never
        # user-typed — same discipline as FixedAsset.asset_code/Product.sku.
        partner_code = await self.partner_repo.next_number(company_id)
        partner = Partner(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            company_id=company_id,
            partner_code=partner_code,
            name=name,
            name_ar=name_ar,
            is_company=is_company,
            parent_partner_id=parent_partner_id,
            is_customer=is_customer,
            is_vendor=is_vendor,
            is_employee=is_employee,
            job_title=job_title,
            is_primary_contact=is_primary_contact,
            phone=phone,
            mobile=mobile,
            email=email,
            website=website,
            vat_number=vat_number,
            cr_number=cr_number,
            payment_terms=payment_terms,
            address=address,
        )
        try:
            return await self.partner_repo.add(partner)
        except IntegrityError as e:
            raise ValueError("A partner was created concurrently with the same code — please retry") from e

    async def update_partner(
        self,
        *,
        company_id: UUID,
        partner_id: UUID,
        name: str,
        name_ar: str | None,
        is_company: bool,
        is_customer: bool,
        is_vendor: bool,
        is_employee: bool,
        job_title: str | None,
        is_primary_contact: bool,
        phone: str | None,
        mobile: str | None,
        email: str | None,
        website: str | None,
        vat_number: str | None,
        cr_number: str | None,
        payment_terms: str | None,
        address: dict | None,
    ) -> Partner:
        partner = await self.partner_repo.get_by_id(partner_id)
        if partner is None or partner.company_id != company_id:
            raise LookupError("Partner not found")
        partner.name = name
        partner.name_ar = name_ar
        partner.is_company = is_company
        partner.is_customer = is_customer
        partner.is_vendor = is_vendor
        partner.is_employee = is_employee
        partner.job_title = job_title
        partner.is_primary_contact = is_primary_contact
        partner.phone = phone
        partner.mobile = mobile
        partner.email = email
        partner.website = website
        partner.vat_number = vat_number
        partner.cr_number = cr_number
        partner.payment_terms = payment_terms
        partner.address = address
        return partner

    async def archive_partner(self, *, company_id: UUID, partner_id: UUID) -> Partner:
        import datetime as _dt

        partner = await self.partner_repo.get_by_id(partner_id)
        if partner is None or partner.company_id != company_id:
            raise LookupError("Partner not found")
        # Naive UTC — `deleted_at` is TIMESTAMP WITHOUT TIME ZONE, matching
        # created_at/updated_at's server-side now() on this same table.
        partner.deleted_at = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
        return partner

    async def restore_partner(self, *, company_id: UUID, partner_id: UUID) -> Partner:
        partner = await self.partner_repo.get_by_id(partner_id, include_archived=True)
        if partner is None or partner.company_id != company_id:
            raise LookupError("Partner not found")
        partner.deleted_at = None
        return partner

    async def add_address(
        self,
        *,
        company_id: UUID,
        partner_id: UUID,
        type: str,
        is_default: bool,
        street: str | None,
        city: str | None,
        region: str | None,
        postal_code: str | None,
        country_code: str | None,
    ) -> PartnerAddress:
        assert self.address_repo is not None
        partner = await self.partner_repo.get_by_id(partner_id)
        if partner is None or partner.company_id != company_id:
            raise LookupError("Partner not found")
        if is_default:
            await self.address_repo.unset_other_defaults(company_id, partner_id, type)
        address = PartnerAddress(
            id=uuid.uuid4(),
            company_id=company_id,
            partner_id=partner_id,
            type=type,
            is_default=is_default,
            street=street,
            city=city,
            region=region,
            postal_code=postal_code,
            country_code=country_code,
        )
        return await self.address_repo.add(address)

    async def update_address(
        self,
        *,
        company_id: UUID,
        partner_id: UUID,
        address_id: UUID,
        type: str,
        is_default: bool,
        street: str | None,
        city: str | None,
        region: str | None,
        postal_code: str | None,
        country_code: str | None,
    ) -> PartnerAddress:
        assert self.address_repo is not None
        address = await self.address_repo.get_by_id(company_id, address_id)
        if address is None or address.partner_id != partner_id:
            raise LookupError("Address not found")
        if is_default:
            await self.address_repo.unset_other_defaults(company_id, partner_id, type, exclude_id=address_id)
        address.type = type
        address.is_default = is_default
        address.street = street
        address.city = city
        address.region = region
        address.postal_code = postal_code
        address.country_code = country_code
        return address

    async def delete_address(self, *, company_id: UUID, partner_id: UUID, address_id: UUID) -> None:
        assert self.address_repo is not None
        address = await self.address_repo.get_by_id(company_id, address_id)
        if address is None or address.partner_id != partner_id:
            raise LookupError("Address not found")
        await self.address_repo.delete(address)


class ProductService:
    """FR-CORE-045 — item/service master, consumed by Sales/Purchasing/Inventory."""

    def __init__(
        self,
        product_repo: ProductRepository,
        category_repo: ProductCategoryRepository,
        uom_repo: UnitOfMeasureRepository,
    ):
        self.product_repo = product_repo
        self.category_repo = category_repo
        self.uom_repo = uom_repo

    async def _validate_category_and_uom(
        self, *, company_id: UUID, category_id: UUID | None, uom_id: UUID | None
    ) -> None:
        if category_id is not None:
            category = await self.category_repo.get_by_id(company_id, category_id)
            if category is None:
                raise ValueError("Invalid product category")
        if uom_id is not None:
            uom = await self.uom_repo.get_by_id(company_id, uom_id)
            if uom is None:
                raise ValueError("Invalid unit of measure")

    async def create_product(
        self,
        *,
        tenant_id: UUID,
        company_id: UUID,
        name: str,
        name_ar: str | None = None,
        category_id: UUID | None = None,
        uom_id: UUID | None = None,
        is_stockable: bool = True,
        sales_price: Decimal = Decimal("0"),
        cost_price: Decimal = Decimal("0"),
        price_high: Decimal | None = None,
        price_low: Decimal | None = None,
        default_tax_rate_id: UUID | None = None,
        reorder_point: Decimal | None = None,
    ) -> Product:
        # Owner directive: the SKU is always system-assigned, never
        # user-typed — same discipline FixedAsset.asset_code already has.
        await self._validate_category_and_uom(company_id=company_id, category_id=category_id, uom_id=uom_id)
        sku = await self.product_repo.next_number(company_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            company_id=company_id,
            sku=sku,
            name=name,
            name_ar=name_ar,
            category_id=category_id,
            uom_id=uom_id,
            is_stockable=is_stockable,
            sales_price=sales_price,
            cost_price=cost_price,
            price_high=price_high,
            price_low=price_low,
            default_tax_rate_id=default_tax_rate_id,
            reorder_point=reorder_point,
        )
        try:
            return await self.product_repo.add(product)
        except IntegrityError as e:
            raise ValueError("A product was created concurrently with the same SKU — please retry") from e

    async def update_product(
        self,
        *,
        company_id: UUID,
        product_id: UUID,
        sku: str,
        name: str,
        name_ar: str | None,
        category_id: UUID | None,
        uom_id: UUID | None,
        is_stockable: bool,
        sales_price: Decimal,
        cost_price: Decimal,
        default_tax_rate_id: UUID | None,
        price_high: Decimal | None = None,
        price_low: Decimal | None = None,
        reorder_point: Decimal | None = None,
    ) -> Product:
        product = await self.product_repo.get_by_id(product_id)
        if product is None or product.company_id != company_id:
            raise LookupError("Product not found")
        if sku != product.sku:
            existing = await self.product_repo.get_by_sku(company_id, sku)
            if existing is not None:
                raise ValueError(f"Product SKU already exists: {sku}")
        await self._validate_category_and_uom(company_id=company_id, category_id=category_id, uom_id=uom_id)
        product.sku = sku
        product.name = name
        product.name_ar = name_ar
        product.category_id = category_id
        product.uom_id = uom_id
        product.is_stockable = is_stockable
        product.sales_price = sales_price
        product.cost_price = cost_price
        product.price_high = price_high
        product.price_low = price_low
        product.default_tax_rate_id = default_tax_rate_id
        product.reorder_point = reorder_point
        return product


class ProductCategoryService:
    """Phase 17B — hierarchical product classification (Part 6 of the
    Phase 17 blueprint). Cycle/duplicate/dependency validation lives here,
    not in the route handler, matching this module's Route → Service →
    Repository convention."""

    def __init__(self, category_repo: ProductCategoryRepository, product_repo: ProductRepository):
        self.category_repo = category_repo
        self.product_repo = product_repo

    async def _validate_parent(
        self, *, company_id: UUID, parent_id: UUID | None, editing_id: UUID | None = None
    ) -> None:
        if parent_id is None:
            return
        if editing_id is not None and parent_id == editing_id:
            raise ValueError("A category cannot be its own parent")
        parent = await self.category_repo.get_by_id(company_id, parent_id)
        if parent is None:
            raise ValueError("Invalid parent category")
        if editing_id is None:
            return
        # Walk the proposed parent's ancestor chain — if it ever reaches
        # `editing_id`, assigning `parent_id` would create a cycle. Bounded
        # by `visited` so any pre-existing bad data can't loop forever.
        visited: set[UUID] = {editing_id}
        current = parent
        while current.parent_id is not None:
            if current.parent_id in visited:
                raise ValueError("Circular category hierarchy is not allowed")
            visited.add(current.id)
            current = await self.category_repo.get_by_id(company_id, current.parent_id)
            if current is None:
                break

    async def create_category(
        self, *, company_id: UUID, name: str, parent_id: UUID | None = None
    ) -> ProductCategory:
        name = name.strip()
        if not name:
            raise ValueError("Category name is required")
        await self._validate_parent(company_id=company_id, parent_id=parent_id)
        duplicate = await self.category_repo.find_sibling_by_name(company_id, parent_id, name)
        if duplicate is not None:
            raise ValueError(f"A category named '{name}' already exists at this level")
        category = ProductCategory(id=uuid.uuid4(), company_id=company_id, name=name, parent_id=parent_id)
        return await self.category_repo.add(category)

    async def update_category(
        self, *, company_id: UUID, category_id: UUID, name: str, parent_id: UUID | None
    ) -> ProductCategory:
        category = await self.category_repo.get_by_id(company_id, category_id)
        if category is None:
            raise LookupError("Category not found")
        name = name.strip()
        if not name:
            raise ValueError("Category name is required")
        await self._validate_parent(company_id=company_id, parent_id=parent_id, editing_id=category_id)
        duplicate = await self.category_repo.find_sibling_by_name(
            company_id, parent_id, name, exclude_id=category_id
        )
        if duplicate is not None:
            raise ValueError(f"A category named '{name}' already exists at this level")
        category.name = name
        category.parent_id = parent_id
        return category

    async def delete_category(self, *, company_id: UUID, category_id: UUID) -> None:
        category = await self.category_repo.get_by_id(company_id, category_id)
        if category is None:
            raise LookupError("Category not found")
        child_count = await self.category_repo.count_children(company_id, category_id)
        if child_count > 0:
            raise ValueError("Cannot delete a category that has child categories")
        product_count = await self.product_repo.count_by_category(company_id, category_id)
        if product_count > 0:
            raise ValueError("Cannot delete a category that is assigned to one or more products")
        await self.category_repo.delete(category)


class UnitOfMeasureService:
    """Phase 17B — company-scoped UOM lookup. No conversion engine (Phase
    17 blueprint explicitly defers that); the model/API shape below leaves
    room for one without a breaking change (a future `base_uom_id` +
    `ratio` pair could be added without touching these fields)."""

    def __init__(self, uom_repo: UnitOfMeasureRepository):
        self.uom_repo = uom_repo

    async def create_uom(
        self, *, company_id: UUID, name: str, code: str, name_ar: str | None = None
    ) -> UnitOfMeasure:
        name = name.strip()
        code = code.strip()
        if not name:
            raise ValueError("Unit of measure name is required")
        if not code:
            raise ValueError("Unit of measure code is required")
        existing = await self.uom_repo.get_by_code(company_id, code)
        if existing is not None:
            raise ValueError(f"Unit of measure code already exists: {code}")
        uom = UnitOfMeasure(id=uuid.uuid4(), company_id=company_id, name=name, name_ar=name_ar, code=code)
        try:
            return await self.uom_repo.add(uom)
        except IntegrityError as e:
            raise ValueError(f"Unit of measure code already exists: {code}") from e

    async def update_uom(
        self,
        *,
        company_id: UUID,
        uom_id: UUID,
        name: str,
        code: str,
        name_ar: str | None,
        active: bool,
    ) -> UnitOfMeasure:
        uom = await self.uom_repo.get_by_id(company_id, uom_id)
        if uom is None:
            raise LookupError("Unit of measure not found")
        name = name.strip()
        code = code.strip()
        if not name:
            raise ValueError("Unit of measure name is required")
        if not code:
            raise ValueError("Unit of measure code is required")
        existing = await self.uom_repo.get_by_code(company_id, code)
        if existing is not None and existing.id != uom_id:
            raise ValueError(f"Unit of measure code already exists: {code}")
        # Deactivating only flips `active` — existing product.uom_id FKs are
        # untouched, so no product ever silently loses its UOM reference.
        uom.name = name
        uom.name_ar = name_ar
        uom.code = code
        uom.active = active
        return uom
