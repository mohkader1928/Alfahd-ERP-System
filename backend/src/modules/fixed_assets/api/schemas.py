"""Pydantic schemas for Fixed Assets (P0-5, 3-Day Brief)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class FixedAssetCategoryCreateRequest(BaseModel):
    name: str
    parent_id: UUID | None = None


class FixedAssetCategoryUpdateRequest(BaseModel):
    name: str
    parent_id: UUID | None = None


class FixedAssetCategoryOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    parent_id: UUID | None

    model_config = {"from_attributes": True}


class FixedAssetCreateRequest(BaseModel):
    name: str
    name_ar: str | None = None
    category_id: UUID | None = None
    fixed_asset_account_id: UUID
    accumulated_depreciation_account_id: UUID
    depreciation_expense_account_id: UUID
    funding_account_id: UUID
    acquisition_date: date
    cost: Decimal
    salvage_value: Decimal = Decimal("0")
    useful_life_months: int


class FixedAssetOut(BaseModel):
    id: UUID
    company_id: UUID
    asset_code: str
    name: str
    name_ar: str | None
    category_id: UUID | None
    fixed_asset_account_id: UUID
    accumulated_depreciation_account_id: UUID
    depreciation_expense_account_id: UUID
    acquisition_date: date
    cost: Decimal
    salvage_value: Decimal
    useful_life_months: int
    accumulated_depreciation: Decimal
    net_book_value: Decimal
    fully_depreciated: bool
    status: str
    disposed_at: date | None
    disposal_proceeds: Decimal | None


class DepreciationEntryOut(BaseModel):
    id: UUID
    period_month: date
    amount: Decimal
    journal_entry_id: UUID

    model_config = {"from_attributes": True}


class RunDepreciationRequest(BaseModel):
    period_month: date
    category_id: UUID | None = None


class RunDepreciationResultRow(BaseModel):
    asset_id: UUID
    asset_code: str
    amount: Decimal | None = None
    reason: str | None = None


class RunDepreciationResponse(BaseModel):
    period_month: date
    assets_posted: int
    assets_skipped: int
    total_amount: Decimal
    posted: list[RunDepreciationResultRow]
    skipped: list[RunDepreciationResultRow]


class DisposeAssetRequest(BaseModel):
    disposal_date: date
    proceeds: Decimal = Decimal("0")
    proceeds_account_id: UUID | None = None
    gain_loss_account_id: UUID | None = None


class AssetCardLine(BaseModel):
    date: date
    movement_type: str
    reference: str
    journal_entry_id: UUID | None
    cost_movement: Decimal
    accumulated_depreciation_movement: Decimal
    running_cost: Decimal
    running_accumulated_depreciation: Decimal
    running_net_book_value: Decimal


class AssetCardResponse(BaseModel):
    asset_id: UUID
    asset_code: str
    asset_name: str
    date_from: date
    date_to: date
    opening_cost: Decimal
    opening_accumulated_depreciation: Decimal
    opening_net_book_value: Decimal
    lines: list[AssetCardLine]
    closing_cost: Decimal
    closing_accumulated_depreciation: Decimal
    closing_net_book_value: Decimal


class ReconciliationAccountRow(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    register_total: Decimal
    gl_balance: Decimal
    difference: Decimal
    matches: bool


class ReconciliationResponse(BaseModel):
    as_of_date: date
    accounts: list[ReconciliationAccountRow]
    total_register_cost: Decimal
    total_register_accumulated_depreciation: Decimal
    total_register_net_book_value: Decimal
    fully_matched: bool


class DepreciationScheduleLine(BaseModel):
    period_month: date
    asset_id: UUID
    asset_code: str
    asset_name: str
    amount: Decimal


class DepreciationScheduleResponse(BaseModel):
    date_from: date
    date_to: date
    lines: list[DepreciationScheduleLine]
    total_amount: Decimal
