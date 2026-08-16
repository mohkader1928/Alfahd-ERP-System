"""Pydantic schemas for Company Profile + Sizing Engine (Adaptive ERP Stage 2.1-2.2)."""

from datetime import datetime
from typing import Any, Literal
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


class BlueprintDecisionOut(BaseModel):
    key: str
    category: str
    decision: Any
    reason: str
    actionable: bool


class ErpBlueprintOut(BaseModel):
    id: UUID
    company_id: UUID
    company_profile_id: UUID
    sizing_result_id: UUID
    blueprint_version: int
    status: str
    decisions: list[BlueprintDecisionOut]
    enabled_modules: dict[str, bool]
    approved_at: datetime | None
    approved_by: UUID | None
    superseded_by_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfigurationPlanItemOut(BaseModel):
    id: UUID
    plan_id: UUID
    decision_key: str
    target_type: str
    action: str
    payload: dict[str, Any]
    status: str
    result: dict[str, Any]
    error_message: str | None
    applied_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfigurationPlanOut(BaseModel):
    id: UUID
    company_id: UUID
    blueprint_id: UUID
    status: str
    validated_at: datetime | None
    applied_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    items: list[ConfigurationPlanItemOut] = []

    model_config = {"from_attributes": True}


class CapabilityMatrixEntryOut(BaseModel):
    """One ERP Blueprint decision, reshaped for commercial/implementation
    consumption -- key/category/decision/reason/actionable are the exact
    fields already on BlueprintDecisionOut; the rest are pure derivations,
    never a second source of truth."""

    key: str
    category: str
    decision: Any
    reason: str
    actionable: bool
    is_gap: bool
    needs_development: bool
    applied_status: str | None = None


class FutureNeedOut(BaseModel):
    """A known Core boundary from docs/adaptive/03 §J -- always shown,
    never derived from a per-customer answer (see AssessmentService)."""

    key: str
    note: str


class CommercialInputsOut(BaseModel):
    """Structured inputs for a future, separate Pricing Engine -- numbers
    only, never a price. See docs/adaptive/07-editions-and-growth-model.md."""

    employee_count: int | None
    desired_user_count: int | None
    branch_count: int | None
    warehouse_count: int | None
    monthly_sales_order_volume: int | None
    monthly_purchase_order_volume: int | None
    sku_count_estimate: int | None
    fixed_asset_count_estimate: int | None
    dimension_scores: dict[str, DimensionScoreOut]
    recommended_edition_label: str | None
    actionable_capability_count: int
    gap_capability_count: int
    custom_development_needed_count: int


class CustomerAssessmentOut(BaseModel):
    """Customer Assessment / Implementation Summary -- a read-only view
    over Profile -> Sizing -> Blueprint -> Configuration Plan, all already
    real, versioned, audited records (see AssessmentService docstring).
    Any field below may be null if that stage of onboarding hasn't
    happened yet for this company (e.g. profile filled but sizing not run
    yet) -- this is never an error, just an incomplete-so-far assessment."""

    company_id: UUID
    profile: CompanyProfileOut
    sizing: SizingResultOut | None
    blueprint: ErpBlueprintOut | None
    configuration_plan: ConfigurationPlanOut | None
    capability_matrix: list[CapabilityMatrixEntryOut]
    future_needs: list[FutureNeedOut]
    commercial_inputs: CommercialInputsOut
