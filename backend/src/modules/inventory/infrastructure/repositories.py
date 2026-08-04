"""Repository implementations for Inventory (Phase 8 §7)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.inventory.infrastructure.models import (
    CycleCount,
    CycleCountLine,
    Location,
    StockLayer,
    StockMove,
    StockQuant,
    Warehouse,
)


class WarehouseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, warehouse: Warehouse) -> Warehouse:
        self.session.add(warehouse)
        await self.session.flush()
        return warehouse

    async def get_by_id(self, warehouse_id: UUID) -> Warehouse | None:
        result = await self.session.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
        return result.scalar_one_or_none()

    async def get_default_for_company(self, company_id: UUID) -> Warehouse | None:
        result = await self.session.execute(
            select(Warehouse).where(Warehouse.company_id == company_id, Warehouse.is_default.is_(True))
        )
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID) -> list[Warehouse]:
        result = await self.session.execute(select(Warehouse).where(Warehouse.company_id == company_id))
        return list(result.scalars().all())


class LocationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, location: Location) -> Location:
        self.session.add(location)
        await self.session.flush()
        return location

    async def get_by_id(self, location_id: UUID) -> Location | None:
        result = await self.session.execute(select(Location).where(Location.id == location_id))
        return result.scalar_one_or_none()

    async def list_by_warehouse(self, warehouse_id: UUID) -> list[Location]:
        result = await self.session.execute(select(Location).where(Location.warehouse_id == warehouse_id))
        return list(result.scalars().all())


class StockQuantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, product_id: UUID, location_id: UUID) -> StockQuant | None:
        result = await self.session.execute(
            select(StockQuant).where(StockQuant.product_id == product_id, StockQuant.location_id == location_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, company_id: UUID, product_id: UUID, location_id: UUID) -> StockQuant:
        quant = await self.get(product_id, location_id)
        if quant is not None:
            return quant
        import uuid as _uuid

        quant = StockQuant(id=_uuid.uuid4(), company_id=company_id, product_id=product_id, location_id=location_id)
        self.session.add(quant)
        await self.session.flush()
        return quant

    async def list_by_company(self, company_id: UUID) -> list[StockQuant]:
        result = await self.session.execute(select(StockQuant).where(StockQuant.company_id == company_id))
        return list(result.scalars().all())


class StockLayerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, layer: StockLayer) -> StockLayer:
        self.session.add(layer)
        await self.session.flush()
        return layer

    async def list_available(self, product_id: UUID, location_id: UUID) -> list[StockLayer]:
        result = await self.session.execute(
            select(StockLayer)
            .where(
                StockLayer.product_id == product_id,
                StockLayer.location_id == location_id,
                StockLayer.qty_remaining > 0,
            )
            .order_by(StockLayer.received_at)
        )
        return list(result.scalars().all())


class StockMoveRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, move: StockMove) -> StockMove:
        self.session.add(move)
        await self.session.flush()
        return move

    async def get_by_id(self, move_id: UUID) -> StockMove | None:
        result = await self.session.execute(select(StockMove).where(StockMove.id == move_id))
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID, *, product_id: UUID | None = None) -> list[StockMove]:
        query = select(StockMove).where(StockMove.company_id == company_id)
        if product_id is not None:
            query = query.where(StockMove.product_id == product_id)
        result = await self.session.execute(query.order_by(StockMove.moved_at.desc()))
        return list(result.scalars().all())


class CycleCountRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, cycle_count: CycleCount, lines: list[CycleCountLine]) -> CycleCount:
        self.session.add(cycle_count)
        await self.session.flush()
        for line in lines:
            line.cycle_count_id = cycle_count.id
            self.session.add(line)
        await self.session.flush()
        return cycle_count

    async def get_by_id(self, cycle_count_id: UUID) -> CycleCount | None:
        result = await self.session.execute(select(CycleCount).where(CycleCount.id == cycle_count_id))
        return result.scalar_one_or_none()

    async def get_lines(self, cycle_count_id: UUID) -> list[CycleCountLine]:
        result = await self.session.execute(
            select(CycleCountLine).where(CycleCountLine.cycle_count_id == cycle_count_id)
        )
        return list(result.scalars().all())
