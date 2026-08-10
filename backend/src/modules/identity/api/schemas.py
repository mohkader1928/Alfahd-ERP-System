"""Pydantic request/response schemas (Presentation layer, Phase 8 §2)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class BootstrapRequest(BaseModel):
    tenant_legal_name: str
    company_legal_name: str
    company_legal_name_ar: str
    vat_number: str = Field(min_length=15, max_length=15)
    base_currency_code: str = Field(min_length=3, max_length=3, default="SAR")
    valuation_method: str = Field(pattern="^(fifo|average)$", default="average")
    main_branch_name: str = "Main Branch"
    main_branch_name_ar: str = "الفرع الرئيسي"
    admin_email: EmailStr
    admin_full_name: str
    admin_password: str


class BootstrapResponse(BaseModel):
    tenant_id: UUID
    company_id: UUID
    branch_id: UUID
    admin_user_id: UUID
    admin_role_id: UUID


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TwoFactorLoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TwoFactorRequiredResponse(BaseModel):
    requires_2fa: bool = True


class MyPermissionsOut(BaseModel):
    """FR-CORE-015: lets the frontend gate UI affordances (show/hide Create,
    Edit, Export...) on the caller's own granted permissions for the active
    company, without duplicating RBAC logic client-side. This is UX only —
    `require_permission()` on each endpoint remains the actual security
    boundary; a client that never calls this still can't do anything it
    isn't authorized for."""

    permission_codes: list[str]


class CompanyCreateRequest(BaseModel):
    legal_name: str
    legal_name_ar: str
    vat_number: str = Field(min_length=15, max_length=15)
    base_currency_code: str = Field(min_length=3, max_length=3, default="SAR")
    valuation_method: str = Field(pattern="^(fifo|average)$", default="average")
    main_branch_name: str = "Main Branch"
    main_branch_name_ar: str = "الفرع الرئيسي"


class CompanyOut(BaseModel):
    id: UUID
    legal_name: str
    legal_name_ar: str
    vat_number: str
    cr_number: str | None = None
    valuation_method: str
    logo_path: str | None = None
    po_approval_threshold: Decimal | None = None

    model_config = {"from_attributes": True}


class CompanyUpdateRequest(BaseModel):
    """Settings Architecture Foundation milestone. Deliberately excludes
    base_currency_id and valuation_method — both drive historical monetary/
    costing calculations and changing them post-transactions would corrupt
    already-posted data; re-scoping those as editable needs a dedicated,
    guarded migration path, not a plain field edit. zatca_environment is
    excluded too — switching to "production" has real e-invoicing
    consequences and deserves its own deliberate flow, not a side effect of
    a general company-details save. po_approval_threshold has none of
    those constraints — it's a forward-looking policy switch, not a
    reinterpretation of historical data — so it's editable here."""

    legal_name: str
    legal_name_ar: str
    vat_number: str = Field(min_length=15, max_length=15)
    cr_number: str | None = None
    po_approval_threshold: Decimal | None = None


class BranchCreateRequest(BaseModel):
    name: str
    name_ar: str
    is_main: bool = False


class BranchOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    name_ar: str
    is_main: bool

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    company_id: UUID
    branch_id: UUID | None = None


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_2fa_enabled: bool

    model_config = {"from_attributes": True}


class RoleAssignRequest(BaseModel):
    role_id: UUID


class PermissionOut(BaseModel):
    id: UUID
    code: str
    scope: str

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    id: UUID
    name: str
    is_system: bool

    model_config = {"from_attributes": True}


class RoleDetailOut(BaseModel):
    id: UUID
    name: str
    is_system: bool
    permission_codes: list[str]


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1)


class RoleRenameRequest(BaseModel):
    name: str = Field(min_length=1)


class RolePermissionsUpdateRequest(BaseModel):
    permission_codes: list[str]


class CompanyAccessGrantRequest(BaseModel):
    company_id: UUID
    branch_id: UUID | None = None


class UserListRow(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_2fa_enabled: bool
    role_names: list[str]


class CompanyAccessRow(BaseModel):
    company_id: UUID
    company_name: str
    branch_id: UUID | None
    branch_name: str | None


class UserDetailOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_2fa_enabled: bool
    roles: list[RoleOut]
    company_access: list[CompanyAccessRow]


class AddressIn(BaseModel):
    """Phase 17B: the `partner.address`/`branch.address` JSONB columns had
    no established shape anywhere in the codebase before this phase (never
    populated, never read) — this is a new, minimal shape, not a
    pre-existing contract being preserved."""

    street: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_code: str | None = None


class PartnerCreateRequest(BaseModel):
    name: str
    name_ar: str | None = None
    is_company: bool = True
    parent_partner_id: UUID | None = None
    is_customer: bool = False
    is_vendor: bool = False
    is_employee: bool = False
    job_title: str | None = None
    is_primary_contact: bool = False
    phone: str | None = None
    mobile: str | None = None
    email: str | None = None
    website: str | None = None
    vat_number: str | None = None
    cr_number: str | None = None
    address: AddressIn | None = None


class PartnerUpdateRequest(BaseModel):
    name: str
    name_ar: str | None = None
    is_company: bool = True
    is_customer: bool = False
    is_vendor: bool = False
    is_employee: bool = False
    job_title: str | None = None
    is_primary_contact: bool = False
    phone: str | None = None
    mobile: str | None = None
    email: str | None = None
    website: str | None = None
    vat_number: str | None = None
    cr_number: str | None = None
    address: AddressIn | None = None


class PartnerOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    name_ar: str | None
    is_company: bool
    parent_partner_id: UUID | None
    is_customer: bool
    is_vendor: bool
    is_employee: bool
    job_title: str | None
    is_primary_contact: bool
    phone: str | None
    mobile: str | None
    email: str | None
    website: str | None
    vat_number: str | None
    cr_number: str | None
    address: dict | None
    is_active: bool
    image_path: str | None = None

    model_config = {"from_attributes": True}


class PartnerAddressCreateRequest(BaseModel):
    type: str = Field(pattern="^(billing|shipping|other)$")
    is_default: bool = False
    street: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_code: str | None = None


class PartnerAddressUpdateRequest(BaseModel):
    type: str = Field(pattern="^(billing|shipping|other)$")
    is_default: bool = False
    street: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_code: str | None = None


class PartnerAddressOut(BaseModel):
    id: UUID
    company_id: UUID
    partner_id: UUID
    type: str
    is_default: bool
    street: str | None
    city: str | None
    region: str | None
    postal_code: str | None
    country_code: str | None

    model_config = {"from_attributes": True}


class ProductCategoryCreateRequest(BaseModel):
    name: str
    parent_id: UUID | None = None


class ProductCategoryUpdateRequest(BaseModel):
    name: str
    parent_id: UUID | None = None


class ProductCategoryOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    parent_id: UUID | None

    model_config = {"from_attributes": True}


class UnitOfMeasureCreateRequest(BaseModel):
    name: str
    name_ar: str | None = None
    code: str


class UnitOfMeasureUpdateRequest(BaseModel):
    name: str
    name_ar: str | None = None
    code: str
    active: bool = True


class UnitOfMeasureOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    name_ar: str | None
    code: str
    active: bool

    model_config = {"from_attributes": True}


class ProductCreateRequest(BaseModel):
    sku: str
    name: str
    name_ar: str | None = None
    category_id: UUID | None = None
    uom_id: UUID | None = None
    is_stockable: bool = True
    sales_price: Decimal = Decimal("0")
    cost_price: Decimal = Decimal("0")
    price_high: Decimal | None = None
    price_low: Decimal | None = None
    default_tax_rate_id: UUID | None = None
    reorder_point: Decimal | None = None


class ProductUpdateRequest(BaseModel):
    sku: str
    name: str
    name_ar: str | None = None
    category_id: UUID | None = None
    uom_id: UUID | None = None
    is_stockable: bool = True
    sales_price: Decimal = Decimal("0")
    cost_price: Decimal = Decimal("0")
    price_high: Decimal | None = None
    price_low: Decimal | None = None
    default_tax_rate_id: UUID | None = None
    reorder_point: Decimal | None = None


class ProductOut(BaseModel):
    id: UUID
    company_id: UUID
    sku: str
    name: str
    name_ar: str | None
    category_id: UUID | None
    uom_id: UUID | None
    is_stockable: bool
    sales_price: Decimal
    cost_price: Decimal
    price_high: Decimal | None = None
    price_low: Decimal | None = None
    last_purchase_price: Decimal | None = None
    default_tax_rate_id: UUID | None
    reorder_point: Decimal | None = None
    image_path: str | None = None

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: UUID
    user_id: UUID | None
    target_table: str
    target_id: UUID
    field_name: str
    old_value: str | None
    new_value: str | None
    changed_at: datetime

    model_config = {"from_attributes": True}
