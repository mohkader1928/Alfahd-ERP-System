"""Application services (use-case orchestration) for Inventory, Phase 8 §2."""

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from src.modules.identity.infrastructure.repositories import ProductRepository, RoleRepository
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
from src.modules.notifications.infrastructure.repositories import NotificationRepository

SIX_DP = Decimal("0.000001")


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
        product_repo: ProductRepository | None = None,
        role_repo: RoleRepository | None = None,
        notification_repo: NotificationRepository | None = None,
        location_repo: LocationRepository | None = None,
    ):
        self.quant_repo = quant_repo
        self.layer_repo = layer_repo
        # Optional — low-stock alert wiring (only issue_stock uses these).
        # Callers that don't pass them (most existing ones) get the exact
        # same behavior as before; the check below is skipped entirely.
        self.product_repo = product_repo
        self.role_repo = role_repo
        self.notification_repo = notification_repo
        self.move_repo = move_repo
        # Optional — only product_cardex's warehouse-per-line enrichment
        # uses this; every other call site is unaffected by omitting it.
        self.location_repo = location_repo

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
        move_type: str | None = None,
    ) -> tuple[StockMove, Decimal]:
        """Returns (move, valuation_variance). `valuation_variance` is
        almost always zero -- see the note below for the one real case
        where it isn't, and what the caller is expected to do with it."""
        if qty <= 0:
            raise ValueError("Received quantity must be positive")

        # Row-level lock (docs/16b, finding #2): without it, two concurrent
        # receipts against the same product+location can both read the same
        # starting qty_on_hand and one write silently overwrites the other's.
        quant = await self.quant_repo.get_or_create_for_update(company_id, product_id, location_id)

        valuation_variance = Decimal("0")
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
            # Moving average recompute: (old_qty*old_avg + new_qty*new_cost) / (old_qty+new_qty).
            #
            # The guard here MUST be `!= 0`, not `> 0`. Algebraically,
            # new_total_qty * moving_avg_cost == old_qty*old_avg +
            # qty*unit_cost for ANY new_total_qty != 0 -- i.e. the running
            # "total value" (qty * avg_cost) always conserves exactly the
            # cumulative net value of every receipt, no matter the sign of
            # qty_on_hand. An `> 0` guard breaks that conservation law
            # whenever a receipt arrives while the position is still
            # negative afterward (a product oversold via FR-INV-007's
            # allow_negative path, still not fully replenished): qty_on_hand
            # keeps moving toward zero as intended, but the receipt's VALUE
            # is silently dropped from moving_avg_cost forever, since the
            # `if` body never runs. Found live on a real company: a product
            # driven to -25,000 units by five large vendor returns, then
            # partially replenished by a further receipt that still left it
            # at -24,000 -- that last receipt's entire value vanished from
            # the valuation report while the GL (which always posts a
            # receipt's true value regardless of the resulting quantity)
            # correctly kept it, producing a real, silent, growing gap
            # between Inventory Valuation and the Trial Balance.
            #
            # `!= 0` still leaves ONE genuinely unrepresentable case: a
            # receipt that brings a negative position to EXACTLY zero.
            # `old_qty*old_avg + qty*unit_cost` can be any nonzero number
            # there (old_avg and unit_cost are independent costs), but
            # `qty_on_hand` is now 0, and 0 * anything == 0 -- there is no
            # `moving_avg_cost` that can carry a nonzero value at zero
            # quantity. That true-but-unrepresentable amount is real money
            # that already flowed through the GL (every receive/issue posts
            # its own exact value): a positive residual means the negative
            # period's issues understated COGS relative to this receipt's
            # replacement cost; a negative residual means they overstated
            # it. Found live: a real company off by SAR 31,250.56 on a
            # single such crossing. Returned to the caller as
            # `valuation_variance` rather than silently dropped -- the
            # caller posts it against the new Inventory Valuation Variance
            # account (see purchasing/sales callers) so the GL keeps
            # matching this register exactly instead of drifting.
            #
            # Quantized to SIX_DP explicitly (not left to the column's
            # implicit truncation) because this is an ITERATIVE recompute —
            # each result becomes the next receipt's own input, so any
            # per-step rounding error would otherwise compound across a
            # product's whole receiving history.
            old_qty = quant.qty_on_hand
            old_avg = quant.moving_avg_cost
            new_total_qty = old_qty + qty
            if new_total_qty != 0:
                quant.moving_avg_cost = (
                    ((old_qty * old_avg) + (qty * unit_cost)) / new_total_qty
                ).quantize(SIX_DP, rounding=ROUND_HALF_UP)
            else:
                valuation_variance = ((old_qty * old_avg) + (qty * unit_cost)).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )

        quant.qty_on_hand += qty

        move = StockMove(
            id=uuid.uuid4(),
            company_id=company_id,
            product_id=product_id,
            source_location_id=None,
            dest_location_id=location_id,
            qty=qty,
            unit_cost=unit_cost,
            move_type=move_type or ("receipt" if source_table != "cycle_count_line" else "adjustment"),
            source_table=source_table,
            source_id=source_id,
        )
        added = await self.move_repo.add(move)
        return added, valuation_variance

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

        # Same row-level lock as receive_stock, and for the same reason —
        # also serializes FIFO layer consumption for this product+location,
        # since layers are only ever touched in service of one quant's issue.
        quant = await self.quant_repo.get_or_create_for_update(company_id, product_id, location_id)
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

        # Real gap found live on a real company's books (Inventory
        # Valuation vs GL, off by tens of thousands of SAR on ~150M SAR of
        # throughput): `compute_issue_cost` rounds `total_cost` to 4dp
        # (matching `journal_entry_line`'s Numeric(18,4) column) for the
        # caller's COGS/GRNI journal entry, but this quant's own
        # `moving_avg_cost` carries 6dp and was left untouched -- so the
        # register's implicit remaining value (qty_on_hand * moving_avg_cost,
        # unrounded) silently diverged from what was actually posted to the
        # GL (the rounded total_cost) on every single issue. Over hundreds
        # of large-quantity deliveries/returns, that per-transaction
        # sub-cent rounding compounded into a material, permanent gap.
        # `receive_stock` never has this problem because it recomputes
        # `moving_avg_cost` itself from conserved total value; issues need
        # the same discipline, conserving against the exact `total_cost`
        # that will actually be journaled rather than assuming "value
        # removed == qty * old_avg" exactly. FIFO is unaffected -- its
        # valuation truth lives in `StockLayer.qty_remaining * unit_cost`,
        # not this quant's moving_avg_cost, which valuation() never reads
        # for a fifo company.
        if valuation_method != "fifo":
            old_qty = quant.qty_on_hand
            old_avg = quant.moving_avg_cost
            new_qty = old_qty - qty
            if new_qty != 0:
                quant.moving_avg_cost = ((old_qty * old_avg) - result.total_cost) / new_qty
                quant.moving_avg_cost = quant.moving_avg_cost.quantize(SIX_DP, rounding=ROUND_HALF_UP)

        quant.qty_on_hand -= qty

        await self._notify_if_crossed_low_stock(company_id=company_id, product_id=product_id, qty_issued=qty)

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

    async def _notify_if_crossed_low_stock(self, *, company_id: UUID, product_id: UUID, qty_issued: Decimal) -> None:
        """Fires once, at the moment total qty_on_hand (summed across every
        warehouse/location) crosses from above to at-or-below the product's
        reorder_point — not on every subsequent sale while already low,
        which would just spam the same recipients repeatedly."""
        if self.product_repo is None or self.role_repo is None or self.notification_repo is None:
            return
        product = await self.product_repo.get_by_id(product_id)
        if product is None or product.reorder_point is None:
            return

        # This session is created with autoflush=False (shared/infrastructure/
        # db/session.py), so the qty_on_hand decrement just applied to the
        # in-memory quant above would not otherwise be visible yet to the
        # raw aggregate SELECT below — flush explicitly so "after" reflects
        # this transaction's own pending write, not last-committed state.
        await self.quant_repo.session.flush()
        total_after = await self.quant_repo.qty_on_hand_for_product(company_id, product_id)
        total_before = total_after + qty_issued
        if not (total_before > product.reorder_point >= total_after):
            return

        recipient_ids = await self.role_repo.list_user_ids_with_permission(company_id, "inventory.stock.view")
        notifications = [
            self.notification_repo.build(
                company_id=company_id,
                recipient_user_id=uid,
                type="low_stock",
                title=f"{product.name} is at or below its reorder point",
                body=f"{product.sku}: {total_after} on hand, reorder point is {product.reorder_point}.",
                entity_type="product",
                entity_id=product.id,
                link="/inventory?tab=low-stock",
            )
            for uid in recipient_ids
        ]
        await self.notification_repo.add_many(notifications)

    async def list_moves_for_source(self, company_id: UUID, source_table: str, source_id: UUID) -> list[StockMove]:
        """Sales/Purchase Returns: exposes the move_repo query the callers
        (Sales/Purchasing) need to find an original document's own stock
        moves without reaching past this service into the repository
        layer directly (Phase 8 §2 layering)."""
        return await self.move_repo.list_by_source(company_id, source_table, source_id)

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

        # Owner request: show which warehouse each cardex line actually
        # touched. Same "dest wins, else source" rule signed_qty already
        # uses below -- the location that determines the sign is the one
        # meaningful warehouse for a receipt/delivery; a transfer's two
        # legs each get their own move row already, so this never has to
        # pick between two different warehouses for one line.
        warehouse_by_location: dict[UUID, tuple[UUID, str]] = {}
        if self.location_repo is not None:
            location_ids = {
                (move.dest_location_id or move.source_location_id)
                for move in moves
                if move.dest_location_id or move.source_location_id
            }
            warehouse_by_location = await self.location_repo.warehouse_names_by_location(list(location_ids))

        running = opening
        lines = []
        for move in moves:
            signed_qty = move.qty if move.dest_location_id is not None else -move.qty
            running = running + signed_qty
            location_id = move.dest_location_id or move.source_location_id
            warehouse_id_, warehouse_name = warehouse_by_location.get(location_id, (None, None))
            lines.append(
                {
                    "move": move,
                    "signed_qty": signed_qty,
                    "running_qty": running,
                    "warehouse_id": warehouse_id_,
                    "warehouse_name": warehouse_name,
                }
            )

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
