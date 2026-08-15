"""Pydantic schemas for Company Profile + Sizing Engine (Adaptive ERP Stage 2.1-2.2)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ApprovalRigor = Literal["low", "medium", "high"]


class CompanyProfileWriteRequest(BaseModel):
    """Shared by create (POST) and update (PATCH) — every field optional so
    a PATCH can send only what changed; create validates the full merged
    entity server-side (see CompanyProfileService)."""

    industry: str | None = None
    legal_form: str | None = None
    employee_count: int | None = Field(default=None, ge=0)
    branch_count: int | None = Field(default=None, ge=0)
    cost_center_tracking_needed: bool | None = None
    is_service_business: bool | None = None
    warehouse_count: int | None = Field(default=None, ge=0)
    monthly_sales_order_volume: int | None = Field(default=None, ge=0)
    monthly_purchase_order_volume: int | None = Field(default=None, ge=0)
    sku_count_estimate: int | None = Field(default=None, ge=0)
    coa_depth_preference: int | None = Field(default=None, ge=1, le=4)
    multi_currency_requested: bool | None = None
    withholding_tax_needed: bool | None = None
    owns_fixed_assets: bool | None = None
    fixed_asset_count_estimate: int | None = Field(default=None, ge=0)
    approval_rigor_preference: ApprovalRigor | None = None
    desired_user_count: int | None = Field(default=None, ge=0)
    two_factor_required: bool | None = None
    growth_notes: dict | None = None


class CompanyProfileOut(BaseModel):
    id: UUID
    company_id: UUID
    industry: str | None
    legal_form: str | None
    employee_count: int | None
    branch_count: int | None
    cost_center_tracking_needed: bool
    is_service_business: bool
    warehouse_count: int | None
    monthly_sales_order_volume: int | None
    monthly_purchase_order_volume: int | None
    sku_count_estimate: int | None
    coa_depth_preference: int | None
    multi_currency_requested: bool
    withholding_tax_needed: bool
    owns_fixed_assets: bool
    fixed_asset_count_estimate: int | None
    approval_rigor_preference: str
    desired_user_count: int | None
    two_factor_required: bool
    growth_notes: dict

    model_config = {"from_attributes": True}


class DimensionScoreOut(BaseModel):
    score: int
    reason: str


class SizingResultOut(BaseModel):
    id: UUID
    company_id: UUID
    company_profile_id: UUID
    rule_version: str
    dimension_scores: dict[str, DimensionScoreOut]
    created_at: datetime

    model_config = {"from_attributes": True}
