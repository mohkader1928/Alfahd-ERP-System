"""Repository implementations for Inventory (Phase 8 §7)."""

import uuid as _uuid
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
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

    async def warehouse_names_by_location(self, location_ids: list[UUID]) -> dict[UUID, tuple[UUID, str]]:
        """Owner request (Product Cardex detail): batch-resolve a set of
        locations straight to their warehouse id/name, so the cardex line
        loop doesn't do one query per line -- mirrors the batching already
        used for products/warehouses in InventoryValuationReportService.valuation."""
        if not location_ids:
            return {}
        result = await self.session.execute(
            select(Location.id, Warehouse.id, Warehouse.name)
            .join(Warehouse, Warehouse.id == Location.warehouse_id)
            .where(Location.id.in_(location_ids))
        )
        return {row[0]: (row[1], row[2]) for row in result.all()}


class StockQuantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, product_id: UUID, location_id: UUID) -> StockQuant | None:
        result = await self.session.execute(
            select(StockQuant).where(StockQuant.product_id == product_id, StockQuant.location_id == location_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, product_id: UUID, location_id: UUID) -> StockQuant | None:
        """Same lookup as `get`, but takes a row-level lock — for the two
        mutation paths (`receive_stock`/`issue_stock`) that read
        `qty_on_hand` and then write it back in the same transaction.
        Without this, two concurrent moves against the same product+location
        can both read the same starting quantity and one write silently
        overwrites the other's (a lost update — see docs/16b, finding #2).
        Never use this for a read-only query (reports, cycle-count
        snapshots): a lock held for no write is pure unnecessary contention.
        """
        result = await self.session.execute(
            select(StockQuant)
            .where(StockQuant.product_id == product_id, StockQuant.location_id == location_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, company_id: UUID, product_id: UUID, location_id: UUID) -> StockQuant:
        quant = await self.get(product_id, location_id)
        if quant is not None:
            return quant
        return await self._create(company_id, product_id, location_id)

    async def get_or_create_for_update(self, company_id: UUID, product_id: UUID, location_id: UUID) -> StockQuant:
        """Phase-One audit P0 fix (docs/16b finding #2, reproduced live by
        the audit's own regression run): the old check-then-insert
        (get_for_update, then _create if None) has a real race — a row that
        doesn't exist yet can't be locked, so two concurrent first-time
        receipts for the same product+location both see None and both try
        to INSERT, and the second hits ux_stock_quant_product_location's
        UniqueViolationError. INSERT ... ON CONFLICT DO UPDATE is atomic and
        takes the same row-level lock a SELECT ... FOR UPDATE would, on
        whichever row survives (freshly inserted, or the pre-existing one it
        collided with) — so the follow-up get_for_update always finds an
        already-locked row instead of racing to create one.
        """
        stmt = (
            pg_insert(StockQuant)
            .values(id=_uuid.uuid4(), company_id=company_id, product_id=product_id, location_id=location_id)
            .on_conflict_do_update(
                index_elements=["product_id", "location_id"],
                set_={"id": StockQuant.id},
            )
        )
        await self.session.execute(stmt)
        quant = await self.get_for_update(product_id, location_id)
        assert quant is not None
        return quant

    async def _create(self, company_id: UUID, product_id: UUID, location_id: UUID) -> StockQuant:
        import uuid as _uuid

        quant = StockQuant(id=_uuid.uuid4(), company_id=company_id, product_id=product_id, location_id=location_id)
        self.session.add(quant)
        await self.session.flush()
        return quant

    async def list_by_company(self, company_id: UUID) -> list[StockQuant]:
        result = await self.session.execute(select(StockQuant).where(StockQuant.company_id == company_id))
        return list(result.scalars().all())

    async def list_by_warehouse(self, company_id: UUID, warehouse_id: UUID) -> list[StockQuant]:
        """Owner request (Cycle Count creation): every quant this
        warehouse's own book balance says is nonzero, so picking a
        warehouse pre-populates the count sheet with what's actually
        supposed to be there instead of starting from a blank product
        picker. Zero-qty quants are excluded -- a cycle count worth
        auto-listing is one with a real book balance to verify; a
        product physically found where none was expected is still
        addable via the existing manual add-line control."""
        result = await self.session.execute(
            select(StockQuant)
            .join(Location, Location.id == StockQuant.location_id)
            .where(
                StockQuant.company_id == company_id,
                Location.warehouse_id == warehouse_id,
                StockQuant.qty_on_hand != 0,
            )
        )
        return list(result.scalars().all())

    async def qty_on_hand_for_product(self, company_id: UUID, product_id: UUID) -> Decimal:
        """Single-product total across every location — cheaper than
        `qty_on_hand_by_product` when only one product's low-stock
        crossing needs checking (issue_stock's post-issue notification)."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(StockQuant.qty_on_hand), 0)).where(
                StockQuant.company_id == company_id, StockQuant.product_id == product_id
            )
        )
        # Same COALESCE(SUM(...), 0) unscaled-zero quirk as elsewhere in
        # this codebase — quantize explicitly for a consistent type/scale
        # regardless of whether any quant rows matched.
        return Decimal(result.scalar_one()).quantize(Decimal("0.000001"))

    async def qty_on_hand_for_product_in_warehouse(
        self, company_id: UUID, product_id: UUID, warehouse_id: UUID
    ) -> Decimal:
        """Owner request: the balance a Quotation/Sales Order/Purchase
        Order/Transfer line should show next to a product — scoped to one
        specific warehouse (unlike `qty_on_hand_for_product`, which sums
        across every warehouse the company has), since a document's own
        `warehouse_id` is what actually determines which stock it can draw
        from or receive into. A warehouse can have several locations, so
        this joins through `Location` and sums rather than doing a single
        `get(product_id, location_id)` lookup."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(StockQuant.qty_on_hand), 0))
            .select_from(StockQuant)
            .join(Location, Location.id == StockQuant.location_id)
            .where(
                StockQuant.company_id == company_id,
                StockQuant.product_id == product_id,
                Location.warehouse_id == warehouse_id,
            )
        )
        return Decimal(result.scalar_one()).quantize(Decimal("0.000001"))

    async def qty_on_hand_by_product(self, company_id: UUID) -> dict[UUID, Decimal]:
        """Total qty_on_hand per product across every location/warehouse —
        for the low-stock check (FR-INV low stock alerts), which compares
        against a product-level reorder_point, not a single location's
        balance."""
        result = await self.session.execute(
            select(StockQuant.product_id, func.sum(StockQuant.qty_on_hand))
            .where(StockQuant.company_id == company_id)
            .group_by(StockQuant.product_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def qty_on_hand_by_warehouse_for_product(
        self, company_id: UUID, product_id: UUID
    ) -> dict[UUID, Decimal]:
        """Owner request: one product's balance broken down per warehouse
        (not netted into a single total like `qty_on_hand_for_product`),
        so the "stock balance by product" report can show every warehouse
        on its own row. Only warehouses with at least one quant row for
        this product come back here -- the route zero-fills the rest from
        the company's full warehouse list, same reasoning as
        `qty_on_hand_for_product_in_warehouse`'s Location join."""
        result = await self.session.execute(
            select(Location.warehouse_id, func.coalesce(func.sum(StockQuant.qty_on_hand), 0))
            .select_from(StockQuant)
            .join(Location, Location.id == StockQuant.location_id)
            .where(StockQuant.company_id == company_id, StockQuant.product_id == product_id)
            .group_by(Location.warehouse_id)
        )
        return {row[0]: Decimal(str(row[1])).quantize(Decimal("0.000001")) for row in result.all()}


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

    async def list_by_source(self, company_id: UUID, source_table: str, source_id: UUID) -> list[StockMove]:
        """Sales/Purchase Returns: looks up the exact moves (and their
        per-line unit_cost) an original document already created, so a
        return can restock at the same cost the original sale/receipt
        used rather than recomputing it from the current valuation state."""
        result = await self.session.execute(
            select(StockMove).where(
                StockMove.company_id == company_id,
                StockMove.source_table == source_table,
                StockMove.source_id == source_id,
            )
        )
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

    async def next_number(self, company_id: UUID) -> str:
        """CC-###### -- a Cycle Count is its own document type, same
        precedent as every other document series in this codebase.
        MAX-based (not COUNT-based): scans existing CC-prefixed numbers
        for their real highest suffix, so it can never re-issue one
        already taken regardless of historical gaps or interleaving --
        see VendorBillRepository.next_number's docstring for the exact
        live collision a COUNT-based approach caused elsewhere."""
        result = await self.session.execute(
            select(CycleCount.number).where(
                CycleCount.company_id == company_id, CycleCount.number.like("CC-%")
            )
        )
        max_seq = 0
        for (number,) in result.all():
            suffix = number.split("-", 1)[1] if "-" in number else ""
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
        return f"CC-{max_seq + 1:06d}"

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
