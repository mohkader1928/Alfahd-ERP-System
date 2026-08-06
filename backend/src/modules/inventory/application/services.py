"""Application services (use-case orchestration) for Inventory, Phase 8 §2."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from src.modules.inventory.domain.entities import InsufficientStockError
from src.modules.inventory.domain.valuation.average import AverageValuationStrategy
from src.modules.inventory.domain.valuation.fifo import FifoValuationStrategy
from src.modules.inventory.domain.valuation.strategy import IssueResult, IValuationStrategy, Layer
from src.modules.inventory.infrastructure.models import (
    CycleCount,
    CycleCountLine,
    Location,
    StockLayer,
    StockMove,
    Warehouse,
)
from src.modules.inventory.infrastructure.repositories import (
    CycleCountRepository,
    LocationRepository,
    StockLayerRepository,
    StockMoveRepository,
    StockQuantRepository,
    WarehouseRepository,
)


def get_valuation_strategy(valuation_method: str) -> IValuationStrategy:
    """Strategy selection (Phase 8 §7) keyed off `company.valuation_method`,
    set once at company registration (Phase 7 §2) and never mixed per-move —
    matches the Phase 5 §4 design note that both structures exist in the
    schema but only one is active per company."""
    if valuation_method == "fifo":
        return FifoValuationStrategy()
    if valuation_method == "average":
        return AverageValuationStrategy()
    raise ValueError(f"Unknown valuation method: {valuation_method}")


class WarehouseService:
    """UC-INV groundwork — warehouse/location setup (FR-INV-001)."""

    def __init__(self, warehouse_repo: WarehouseRepository, location_repo: LocationRepository):
        self.warehouse_repo = warehouse_repo
        self.location_repo = location_repo

    async def create_warehouse_with_default_location(
        self, *, company_id: UUID, branch_id: UUID, name: str, is_default: bool = False
    ) -> tuple[Warehouse, Location]:
        if is_default:
            await self.warehouse_repo.clear_default_for_company(company_id)
        warehouse = Warehouse(id=uuid.uuid4(), company_id=company_id, branch_id=branch_id, name=name, is_default=is_default)
        await self.warehouse_repo.add(warehouse)

        location = Location(id=uuid.uuid4(), company_id=company_id, warehouse_id=warehouse.id, name=f"{name} - Stock")
        await self.location_repo.add(location)
        return warehouse, location

    async def set_default_warehouse(self, *, company_id: UUID, warehouse_id: UUID) -> Warehouse:
        warehouse = await self.warehouse_repo.get_by_id(warehouse_id)
        if warehouse is None or warehouse.company_id != company_id:
            raise ValueError("Warehouse not found")
        await self.warehouse_repo.clear_default_for_company(company_id)
        warehouse.is_default = True
        return warehouse


class InventoryValuationService:
    """Core valuation engine (FR-INV-004/005) — shared by receipts,
    issues (deliveries/sales), transfers, and adjustments. Every
    valuation-affecting call returns enough data for the caller to post the
    matching journal entry (FR-SAL-007 / Phase 5 §4), but does not post it
    itself — that stays the caller's responsibility (Sales, Purchasing, or
    the Cycle Count flow), consistent with how Sales posts its own entries.
    """

    def __init__(
        self,
        quant_repo: StockQuantRepository,
        layer_repo: StockLayerRepository,
        move_repo: StockMoveRepository,
    ):
        self.quant_repo = quant_repo
        self.layer_repo = layer_repo
        self.move_repo = move_repo

    async def receive_stock(
        self,
        *,
        company_id: UUID,
        product_id: UUID,
        location_id: UUID,
        qty: Decimal,
        unit_cost: Decimal,
        valuation_method: str,
        source_table: str,
        source_id: UUID,
    ) -> StockMove:
        if qty <= 0:
            raise ValueError("Received quantity must be positive")

        quant = await self.quant_repo.get_or_create(company_id, product_id, location_id)

        if valuation_method == "fifo":
            layer = StockLayer(
                id=uuid.uuid4(),
                company_id=company_id,
                product_id=product_id,
                location_id=location_id,
                qty_remaining=qty,
                unit_cost=unit_cost,
            )
            await self.layer_repo.add(layer)
        else:
            # Moving average recompute: (old_qty*old_avg + new_qty*new_cost) / (old_qty+new_qty)
            new_total_qty = quant.qty_on_hand + qty
            if new_total_qty > 0:
                quant.moving_avg_cost = (
                    (quant.qty_on_hand * quant.moving_avg_cost) + (qty * unit_cost)
                ) / new_total_qty

        quant.qty_on_hand += qty

        move = StockMove(
            id=uuid.uuid4(),
            company_id=company_id,
            product_id=product_id,
            source_location_id=None,
            dest_location_id=location_id,
            qty=qty,
            unit_cost=unit_cost,
            move_type="receipt" if source_table != "cycle_count_line" else "adjustment",
            source_table=source_table,
            source_id=source_id,
        )
        return await self.move_repo.add(move)

    async def issue_stock(
        self,
        *,
        company_id: UUID,
        product_id: UUID,
        location_id: UUID,
        qty: Decimal,
        valuation_method: str,
        source_table: str,
        source_id: UUID,
        move_type: str = "delivery",
        allow_negative: bool = False,
    ) -> tuple[StockMove, Decimal]:
        """Returns (move, total_cost_of_goods_issued) for the caller's
        journal entry (e.g. Sales' Dr COGS / Cr Inventory)."""
        if qty <= 0:
            raise ValueError("Issued quantity must be positive")

        quant = await self.quant_repo.get_or_create(company_id, product_id, location_id)
        strategy = get_valuation_strategy(valuation_method)

        if valuation_method == "fifo":
            layer_rows = await self.layer_repo.list_available(product_id, location_id)
            layers = [
                Layer(id=row.id, qty_remaining=row.qty_remaining, unit_cost=row.unit_cost, received_at=row.received_at)
                for row in layer_rows
            ]
        else:
            layers = [Layer(id=uuid.uuid4(), qty_remaining=quant.qty_on_hand, unit_cost=quant.moving_avg_cost, received_at=datetime.now(UTC))]

        try:
            result = strategy.compute_issue_cost(qty, layers=layers, moving_avg_cost=quant.moving_avg_cost)
        except InsufficientStockError:
            if not allow_negative:
                raise
            # FR-INV-007 override: proceed at the last-known unit cost,
            # taking the stock balance negative rather than blocking the move.
            result = IssueResult(
                total_cost=qty * quant.moving_avg_cost, unit_cost=quant.moving_avg_cost, consumed=[]
            )

        if valuation_method == "fifo" and result.consumed:
            layer_by_id = {row.id: row for row in layer_rows}
            for layer_id, qty_consumed in result.consumed:
                layer_by_id[layer_id].qty_remaining -= qty_consumed

        quant.qty_on_hand -= qty

        move = StockMove(
            id=uuid.uuid4(),
            company_id=company_id,
            product_id=product_id,
            source_location_id=location_id,
            dest_location_id=None,
            qty=qty,
            unit_cost=result.unit_cost,
            move_type=move_type,
            source_table=source_table,
            source_id=source_id,
        )
        await self.move_repo.add(move)
        return move, result.total_cost

    async def product_cardex(
        self,
        *,
        company_id: UUID,
        product_id: UUID,
        date_from: date,
        date_to: date,
        warehouse_id: UUID | None = None,
        source_table: str | None = None,
    ) -> dict:
        """Bundle E — standard product cardex (Owner-requested): opening
        quantity (all activity strictly before `date_from`), every move in
        range with a running balance, and a closing quantity — the exact
        same opening/running/closing shape `AccountingService.general_ledger`
        already establishes for one account's ledger, applied to one
        product's stock instead."""
        opening = await self.move_repo.opening_qty(
            company_id, product_id, before_date=date_from, warehouse_id=warehouse_id
        )
        moves = await self.move_repo.cardex_lines(
            company_id,
            product_id,
            date_from=date_from,
            date_to=date_to,
            warehouse_id=warehouse_id,
            source_table=source_table,
        )

        running = opening
        lines = []
        for move in moves:
            signed_qty = move.qty if move.dest_location_id is not None else -move.qty
            running = running + signed_qty
            lines.append({"move": move, "signed_qty": signed_qty, "running_qty": running})

        return {"opening_qty": opening, "lines": lines, "closing_qty": running}


class CycleCountService:
    """UC-INV-02 — Cycle Count / Inventory Adjustment (FR-INV-006)."""

    def __init__(self, cycle_count_repo: CycleCountRepository, quant_repo: StockQuantRepository):
        self.cycle_count_repo = cycle_count_repo
        self.quant_repo = quant_repo

    async def create_cycle_count(
        self, *, company_id: UUID, warehouse_id: UUID, scheduled_date: date, lines: list[dict]
    ) -> CycleCount:
        cycle_count = CycleCount(
            id=uuid.uuid4(), company_id=company_id, warehouse_id=warehouse_id, scheduled_date=scheduled_date
        )
        orm_lines = []
        for line in lines:
            quant = await self.quant_repo.get(line["product_id"], line["location_id"])
            system_qty = quant.qty_on_hand if quant else Decimal("0")
            orm_lines.append(
                CycleCountLine(
                    id=uuid.uuid4(),
                    company_id=company_id,
                    product_id=line["product_id"],
                    location_id=line["location_id"],
                    system_qty=system_qty,
                    counted_qty=Decimal(str(line["counted_qty"])),
                )
            )
        return await self.cycle_count_repo.add(cycle_count, orm_lines)
