"""FastAPI dependencies for Inventory."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.modules.identity.infrastructure.repositories import CompanyRepository
from src.modules.inventory.infrastructure.repositories import (
    CycleCountRepository,
    LocationRepository,
    StockLayerRepository,
    StockMoveRepository,
    StockQuantRepository,
    WarehouseRepository,
)
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext, get_auth_context


def get_warehouse_repo(db: AsyncSession = Depends(get_db)) -> WarehouseRepository:
    return WarehouseRepository(db)


def get_location_repo(db: AsyncSession = Depends(get_db)) -> LocationRepository:
    return LocationRepository(db)


def get_stock_quant_repo(db: AsyncSession = Depends(get_db)) -> StockQuantRepository:
    return StockQuantRepository(db)


def get_stock_layer_repo(db: AsyncSession = Depends(get_db)) -> StockLayerRepository:
    return StockLayerRepository(db)


def get_stock_move_repo(db: AsyncSession = Depends(get_db)) -> StockMoveRepository:
    return StockMoveRepository(db)


def get_cycle_count_repo(db: AsyncSession = Depends(get_db)) -> CycleCountRepository:
    return CycleCountRepository(db)


async def get_company_valuation_method(
    db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context)
) -> str:
    company = await CompanyRepository(db).get_by_id(ctx.company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company.valuation_method
