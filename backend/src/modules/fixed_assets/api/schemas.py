"""Pydantic schemas for Fixed Assets (P0-5, 3-Day Brief)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class FixedAssetCreateRequest(BaseModel):
    name: str
    name_ar: str | None = None
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
