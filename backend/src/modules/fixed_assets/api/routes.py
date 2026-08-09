"""FastAPI routes for Fixed Assets (P0-5, 3-Day Brief)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.fixed_assets.api.deps import get_fixed_asset_service, require_permission
from src.modules.fixed_assets.api.schemas import (
    DepreciationEntryOut,
    DisposeAssetRequest,
    FixedAssetCreateRequest,
    FixedAssetOut,
    RunDepreciationRequest,
    RunDepreciationResponse,
)
from src.modules.fixed_assets.application.services import FixedAssetService
from src.modules.fixed_assets.domain.entities import AssetAlreadyDisposedError
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext

router = APIRouter()


@router.get("", response_model=list[FixedAssetOut])
async def list_fixed_assets(
    ctx: AuthContext = Depends(require_permission("fixed_assets.view")),
    service: FixedAssetService = Depends(get_fixed_asset_service),
):
    return await service.list_assets(ctx.company_id)


@router.get("/{asset_id}", response_model=FixedAssetOut)
async def get_fixed_asset(
    asset_id: UUID,
    ctx: AuthContext = Depends(require_permission("fixed_assets.view")),
    service: FixedAssetService = Depends(get_fixed_asset_service),
):
    asset = await service.get_asset(ctx.company_id, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixed asset not found")
    return asset


@router.get("/{asset_id}/depreciation-entries", response_model=list[DepreciationEntryOut])
async def list_depreciation_entries(
    asset_id: UUID,
    ctx: AuthContext = Depends(require_permission("fixed_assets.view")),
    service: FixedAssetService = Depends(get_fixed_asset_service),
):
    try:
        return await service.list_depreciation_entries(ctx.company_id, asset_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.post("", response_model=FixedAssetOut, status_code=status.HTTP_201_CREATED)
async def create_fixed_asset(
    payload: FixedAssetCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("fixed_assets.create", require_branch=True)),
    service: FixedAssetService = Depends(get_fixed_asset_service),
):
    try:
        asset = await service.create_asset(
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            name=payload.name,
            name_ar=payload.name_ar,
            fixed_asset_account_id=payload.fixed_asset_account_id,
            accumulated_depreciation_account_id=payload.accumulated_depreciation_account_id,
            depreciation_expense_account_id=payload.depreciation_expense_account_id,
            funding_account_id=payload.funding_account_id,
            acquisition_date=payload.acquisition_date,
            cost=payload.cost,
            salvage_value=payload.salvage_value,
            useful_life_months=payload.useful_life_months,
            created_by=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    # Read the computed representation BEFORE commit: `set_company_context`
    # uses SET LOCAL (transaction-scoped, see session.py), so a query issued
    # after db.commit() runs in a fresh transaction with no company context
    # set — RLS then can't cast the empty GUC to uuid and every read fails.
    result = await service.get_asset(ctx.company_id, asset.id)
    await db.commit()
    return result


@router.post(":run-depreciation", response_model=RunDepreciationResponse)
async def run_depreciation(
    payload: RunDepreciationRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("fixed_assets.depreciation.run", require_branch=True)),
    service: FixedAssetService = Depends(get_fixed_asset_service),
):
    try:
        result = await service.run_depreciation(
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            period_month=payload.period_month,
            created_by=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return result


@router.post("/{asset_id}:dispose", response_model=FixedAssetOut)
async def dispose_fixed_asset(
    asset_id: UUID,
    payload: DisposeAssetRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("fixed_assets.dispose", require_branch=True)),
    service: FixedAssetService = Depends(get_fixed_asset_service),
):
    try:
        await service.dispose_asset(
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            asset_id=asset_id,
            disposal_date=payload.disposal_date,
            proceeds=payload.proceeds,
            proceeds_account_id=payload.proceeds_account_id,
            gain_loss_account_id=payload.gain_loss_account_id,
            created_by=ctx.user_id,
        )
    except (AssetAlreadyDisposedError, ValueError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    result = await service.get_asset(ctx.company_id, asset_id)  # see comment in create_fixed_asset
    await db.commit()
    return result
