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


class CompanyOut(BaseModel):
    id: UUID
    legal_name: str
    legal_name_ar: str
    vat_number: str
    valuation_method: str

    model_config = {"from_attributes": True}


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


class PartnerCreateRequest(BaseModel):
    name: str
    name_ar: str | None = None
    is_customer: bool = False
    is_vendor: bool = False
    vat_number: str | None = None
    cr_number: str | None = None


class PartnerOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    name_ar: str | None
    is_customer: bool
    is_vendor: bool
    vat_number: str | None

    model_config = {"from_attributes": True}


class ProductCreateRequest(BaseModel):
    sku: str
    name: str
    name_ar: str | None = None
    is_stockable: bool = True
    sales_price: Decimal = Decimal("0")
    cost_price: Decimal = Decimal("0")
    default_tax_rate_id: UUID | None = None


class ProductOut(BaseModel):
    id: UUID
    company_id: UUID
    sku: str
    name: str
    name_ar: str | None
    is_stockable: bool
    sales_price: Decimal
    default_tax_rate_id: UUID | None

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
