"""FastAPI routes for Fixed Assets (P0-5, 3-Day Brief)."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.fixed_assets.api.deps import (
    get_fixed_asset_category_repo,
    get_fixed_asset_category_service,
    get_fixed_asset_service,
    require_permission,
)
from src.modules.fixed_assets.api.schemas import (
    AssetCardResponse,
    DepreciationEntryOut,
    DepreciationScheduleResponse,
    DisposeAssetRequest,
    FixedAssetCategoryCreateRequest,
    FixedAssetCategoryOut,
    FixedAssetCategoryUpdateRequest,
    FixedAssetCreateRequest,
    FixedAssetOut,
    ReconciliationResponse,
    RunDepreciationRequest,
    RunDepreciationResponse,
)
from src.modules.fixed_assets.application.services import (
    FixedAssetCategoryService,
    FixedAssetService,
)
from src.modules.fixed_assets.domain.entities import AssetAlreadyDisposedError
from src.modules.fixed_assets.infrastructure.repositories import FixedAssetCategoryRepository
from src.modules.identity.api.deps import get_company_repo
from src.modules.identity.infrastructure.repositories import CompanyRepository
from src.shared.infrastructure.db.session import get_db
from src.shared.reporting.company_name import resolve_company_name
from src.shared.reporting.export_render import ReportColumn, ReportTable
from src.shared.reporting.export_response import build_export_response
from src.shared.reporting.formatting import format_amount, format_date_str
from src.shared.reporting.labels import label, title
from src.shared.security.auth_context import AuthContext

router = APIRouter()

ExportFormatParam = Literal["json", "pdf", "xlsx"]


def _register_table(*, company_name: str, assets: list[dict], lang: str) -> ReportTable:
    rows = [
        [
            a["asset_code"],
            a["name"],
            format_date_str(a["acquisition_date"]),
            format_amount(a["cost"]),
            format_amount(a["accumulated_depreciation"]),
            format_amount(a["net_book_value"]),
            a["status"],
        ]
        for a in assets
    ]
    totals_cost = sum((a["cost"] for a in assets), start=Decimal("0"))
    totals_accum = sum((a["accumulated_depreciation"] for a in assets), start=Decimal("0"))
    totals_nbv = sum((a["net_book_value"] for a in assets), start=Decimal("0"))
    return ReportTable(
        title=title(lang, "fixed_assets_register"),
        company_name=company_name,
        columns=[
            ReportColumn(label(lang, "asset_code")),
            ReportColumn(label(lang, "asset_name")),
            ReportColumn(label(lang, "date")),
            ReportColumn(label(lang, "cost"), "end"),
            ReportColumn(label(lang, "accumulated_depreciation"), "end"),
            ReportColumn(label(lang, "net_book_value"), "end"),
            ReportColumn(label(lang, "status")),
        ],
        rows=rows,
        totals=[
            "",
            "",
            label(lang, "total"),
            format_amount(totals_cost),
            format_amount(totals_accum),
            format_amount(totals_nbv),
            "",
        ],
        rtl=lang == "ar",
    )


@router.get("", response_model=list[FixedAssetOut])
async def list_fixed_assets(
    category_id: UUID | None = None,
    status_filter: Literal["active", "disposed"] | None = None,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("fixed_assets.view")),
    service: FixedAssetService = Depends(get_fixed_asset_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    """Doubles as the Fixed Asset Register report: `format=pdf|xlsx` (with
    an optional `status_filter`/`category_id`) exports the same list the
    plain JSON register screen shows, matching the pattern every other
    module's list-vs-export endpoint already uses."""
    assets = await service.list_assets(ctx.company_id, category_id=category_id, status=status_filter)
    if format == "json":
        return assets
    table = _register_table(
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang), assets=assets, lang=lang
    )
    return build_export_response(format, "fixed-assets-register", table)


@router.get("/depreciation-schedule", response_model=DepreciationScheduleResponse)
async def get_depreciation_schedule(
    date_from: date,
    date_to: date,
    category_id: UUID | None = None,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("fixed_assets.view")),
    service: FixedAssetService = Depends(get_fixed_asset_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    result = await service.get_depreciation_schedule(
        company_id=ctx.company_id, date_from=date_from, date_to=date_to, category_id=category_id
    )
    if format == "json":
        return result
    rows = [
        [
            format_date_str(line["period_month"]),
            line["asset_code"],
            line["asset_name"],
            format_amount(line["amount"]),
        ]
        for line in result["lines"]
    ]
    table = ReportTable(
        title=title(lang, "fixed_assets_depreciation_schedule"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f'{result["date_from"]} — {result["date_to"]}',
        columns=[
            ReportColumn(label(lang, "period")),
            ReportColumn(label(lang, "asset_code")),
            ReportColumn(label(lang, "asset_name")),
            ReportColumn(label(lang, "amount"), "end"),
        ],
        rows=rows,
        totals=["", "", label(lang, "total"), format_amount(result["total_amount"])],
        rtl=lang == "ar",
    )
    return build_export_response(format, "fixed-assets-depreciation-schedule", table)


@router.get("/categories", response_model=list[FixedAssetCategoryOut])
async def list_fixed_asset_categories(
    ctx: AuthContext = Depends(require_permission("fixed_assets.view")),
    category_repo: FixedAssetCategoryRepository = Depends(get_fixed_asset_category_repo),
):
    return await category_repo.list_by_company(ctx.company_id)


@router.post("/categories", response_model=FixedAssetCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_fixed_asset_category(
    payload: FixedAssetCategoryCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("fixed_assets.category.manage")),
    category_service: FixedAssetCategoryService = Depends(get_fixed_asset_category_service),
):
    try:
        category = await category_service.create_category(
            company_id=ctx.company_id, name=payload.name, parent_id=payload.parent_id
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return category


@router.patch("/categories/{category_id}", response_model=FixedAssetCategoryOut)
async def update_fixed_asset_category(
    category_id: UUID,
    payload: FixedAssetCategoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("fixed_assets.category.manage")),
    category_service: FixedAssetCategoryService = Depends(get_fixed_asset_category_service),
):
    try:
        category = await category_service.update_category(
            company_id=ctx.company_id, category_id=category_id, name=payload.name, parent_id=payload.parent_id
        )
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fixed_asset_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("fixed_assets.category.manage")),
    category_service: FixedAssetCategoryService = Depends(get_fixed_asset_category_service),
):
    try:
        await category_service.delete_category(company_id=ctx.company_id, category_id=category_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()


def _reconciliation_table(*, company_name: str, result: dict, lang: str) -> ReportTable:
    rows = [
        [
            r["account_code"],
            r["account_name"],
            format_amount(r["register_total"]),
            format_amount(r["gl_balance"]),
            format_amount(r["difference"]),
        ]
        for r in result["accounts"]
    ]
    return ReportTable(
        title=title(lang, "fixed_assets_reconciliation"),
        company_name=company_name,
        subtitle=f'{label(lang, "date")}: {result["as_of_date"]}',
        columns=[
            ReportColumn(label(lang, "account_code")),
            ReportColumn(label(lang, "account")),
            ReportColumn(label(lang, "register_total"), "end"),
            ReportColumn(label(lang, "gl_balance"), "end"),
            ReportColumn(label(lang, "difference"), "end"),
        ],
        rows=rows,
        totals=[
            "",
            label(lang, "net_book_value"),
            format_amount(result["total_register_cost"]),
            "",
            format_amount(result["total_register_net_book_value"]),
        ],
        rtl=lang == "ar",
    )


@router.get("/reconciliation", response_model=ReconciliationResponse)
async def get_reconciliation(
    as_of_date: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("fixed_assets.view")),
    service: FixedAssetService = Depends(get_fixed_asset_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    result = await service.get_reconciliation(company_id=ctx.company_id, as_of_date=as_of_date)
    if format == "json":
        return result
    table = _reconciliation_table(
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        result=result,
        lang=lang,
    )
    return build_export_response(format, "fixed-assets-reconciliation", table)


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


def _asset_card_table(*, company_name: str, result: dict, lang: str) -> ReportTable:
    rows = [
        [
            format_date_str(line["date"]),
            line["movement_type"],
            line["reference"],
            format_amount(line["running_cost"]),
            format_amount(line["running_accumulated_depreciation"]),
            format_amount(line["running_net_book_value"]),
        ]
        for line in result["lines"]
    ]
    return ReportTable(
        title=f'{title(lang, "fixed_asset_card")} — {result["asset_code"]} {result["asset_name"]}',
        company_name=company_name,
        subtitle=f'{result["date_from"]} — {result["date_to"]}',
        columns=[
            ReportColumn(label(lang, "date")),
            ReportColumn(label(lang, "type")),
            ReportColumn(label(lang, "reference")),
            ReportColumn(label(lang, "cost"), "end"),
            ReportColumn(label(lang, "accumulated_depreciation"), "end"),
            ReportColumn(label(lang, "net_book_value"), "end"),
        ],
        rows=[
            [
                "",
                "",
                label(lang, "opening_balance"),
                format_amount(result["opening_cost"]),
                format_amount(result["opening_accumulated_depreciation"]),
                format_amount(result["opening_net_book_value"]),
            ],
            *rows,
        ],
        totals=[
            "",
            "",
            label(lang, "closing_balance"),
            format_amount(result["closing_cost"]),
            format_amount(result["closing_accumulated_depreciation"]),
            format_amount(result["closing_net_book_value"]),
        ],
        rtl=lang == "ar",
    )


@router.get("/{asset_id}/card", response_model=AssetCardResponse)
async def get_asset_card(
    asset_id: UUID,
    date_from: date,
    date_to: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("fixed_assets.view")),
    service: FixedAssetService = Depends(get_fixed_asset_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    try:
        result = await service.get_asset_card(
            company_id=ctx.company_id, asset_id=asset_id, date_from=date_from, date_to=date_to
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    if format == "json":
        return AssetCardResponse(date_from=date_from, date_to=date_to, **result)
    table = _asset_card_table(
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        result={**result, "date_from": date_from, "date_to": date_to},
        lang=lang,
    )
    return build_export_response(format, f"fixed-asset-card-{result['asset_code']}", table)


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
            category_id=payload.category_id,
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
            category_id=payload.category_id,
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
