"""Repository implementations for Inventory (Phase 8 §7)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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

    async def clear_default_for_company(self, company_id: UUID) -> None:
        """Ensures at most one warehouse per company has is_default=True —
        called before setting a new default (creation or promotion), since
        no DB constraint enforces this (Phase 8 §7 keeps it nullable/plain
        boolean, application-level invariant only)."""
        await self.session.execute(
            update(Warehouse).where(Warehouse.company_id == company_id, Warehouse.is_default.is_(True)).values(is_default=False)
        )


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

    def _warehouse_filter(self, query, warehouse_id: UUID):
        """A move touches a warehouse if either its source or dest location
        belongs to it -- covers receipts/deliveries/adjustments (one side
        set) and transfers (both legs, possibly across warehouses)."""
        source_loc = aliased(Location)
        dest_loc = aliased(Location)
        return query.outerjoin(source_loc, source_loc.id == StockMove.source_location_id).outerjoin(
            dest_loc, dest_loc.id == StockMove.dest_location_id
        ).where(or_(source_loc.warehouse_id == warehouse_id, dest_loc.warehouse_id == warehouse_id))

    async def cardex_lines(
        self,
        company_id: UUID,
        product_id: UUID,
        *,
        date_from: date,
        date_to: date,
        warehouse_id: UUID | None = None,
        source_table: str | None = None,
    ) -> list[StockMove]:
        """Bundle E — standard product cardex: every move for one product in
        [date_from, date_to], optionally narrowed to one warehouse and/or
        one document (source) type."""
        query = select(StockMove).where(
            StockMove.company_id == company_id,
            StockMove.product_id == product_id,
            func.date(StockMove.moved_at) >= date_from,
            func.date(StockMove.moved_at) <= date_to,
        )
        if warehouse_id is not None:
            query = self._warehouse_filter(query, warehouse_id)
        if source_table is not None:
            query = query.where(StockMove.source_table == source_table)
        result = await self.session.execute(query.order_by(StockMove.moved_at, StockMove.id))
        return list(result.scalars().all())

    async def opening_qty(
        self, company_id: UUID, product_id: UUID, *, before_date: date, warehouse_id: UUID | None = None
    ) -> Decimal:
        """Signed quantity on hand strictly before `before_date`: a move
        with a dest location is an increase, one with only a source
        location is a decrease -- covers receipts, deliveries, adjustments,
        and both legs of a transfer uniformly, without needing separate
        per-move-type sign logic."""
        signed_qty = case((StockMove.dest_location_id.is_not(None), StockMove.qty), else_=-StockMove.qty)
        query = select(func.coalesce(func.sum(signed_qty), 0)).where(
            StockMove.company_id == company_id,
            StockMove.product_id == product_id,
            func.date(StockMove.moved_at) < before_date,
        )
        if warehouse_id is not None:
            query = self._warehouse_filter(query, warehouse_id)
        result = await self.session.execute(query)
        # COALESCE's fallback 0 is a plain integer literal with no relation
        # to StockMove.qty's NUMERIC(18,6) scale, so an empty sum comes back
        # as Decimal("0") instead of Decimal("0.000000") -- quantize
        # explicitly so an empty and a non-empty result always match scale.
        return Decimal(str(result.scalar_one())).quantize(Decimal("0.000001"))


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

    async def list_by_company(self, company_id: UUID) -> list[CycleCount]:
        result = await self.session.execute(
            select(CycleCount).where(CycleCount.company_id == company_id).order_by(CycleCount.scheduled_date.desc())
        )
        return list(result.scalars().all())
