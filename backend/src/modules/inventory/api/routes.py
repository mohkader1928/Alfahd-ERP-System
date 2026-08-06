"""FastAPI routes for Inventory, per Phase 10 §6.5 (nucleus scope: no
Goods Receipt yet — M4 will wire Purchasing's receipt into
`InventoryValuationService.receive_stock`; `/stock/receive` is a direct
stand-in used for initial stock entry until then)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.api.deps import (
    get_account_repo,
    get_fiscal_period_repo,
    get_journal_entry_repo,
    get_journal_repo,
)
from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import (
    AccountRepository,
    FiscalPeriodRepository,
    JournalEntryRepository,
    JournalRepository,
)
from src.modules.inventory.api.deps import (
    get_company_valuation_method,
    get_cycle_count_repo,
    get_location_repo,
    get_stock_layer_repo,
    get_stock_move_repo,
    get_stock_quant_repo,
    get_warehouse_repo,
    require_permission,
)
from src.modules.inventory.api.schemas import (
    CardexLineOut,
    CycleCountCreateRequest,
    CycleCountDetailResponse,
    CycleCountOut,
    ProductCardexResponse,
    StockMoveOut,
    StockQuantOut,
    StockReceiveRequest,
    TransferCreateRequest,
    WarehouseCreateRequest,
    WarehouseCreateResponse,
    WarehouseOut,
)
from src.modules.inventory.application.services import (
    CycleCountService,
    InventoryValuationService,
    WarehouseService,
)
from src.modules.inventory.domain.entities import InsufficientStockError
from src.modules.inventory.infrastructure.repositories import (
    CycleCountRepository,
    LocationRepository,
    StockLayerRepository,
    StockMoveRepository,
    StockQuantRepository,
    WarehouseRepository,
)
from src.shared.infrastructure.db.session import get_db, set_company_context
from src.shared.security.auth_context import AuthContext

router = APIRouter()

ACCOUNT_CODE_INVENTORY = "1300"
ACCOUNT_CODE_ADJUSTMENT = "5200"


@router.post("/warehouses", response_model=WarehouseCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    payload: WarehouseCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("inventory.warehouse.manage", require_branch=True)),
    warehouse_repo: WarehouseRepository = Depends(get_warehouse_repo),
    location_repo: LocationRepository = Depends(get_location_repo),
):
    service = WarehouseService(warehouse_repo, location_repo)
    warehouse, location = await service.create_warehouse_with_default_location(
        company_id=ctx.company_id, branch_id=ctx.branch_id, name=payload.name, is_default=payload.is_default
    )
    await db.commit()
    return WarehouseCreateResponse(warehouse=warehouse, default_location=location)


@router.post("/warehouses/{warehouse_id}:set-default", response_model=WarehouseOut)
async def set_default_warehouse(
    warehouse_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("inventory.warehouse.manage")),
    warehouse_repo: WarehouseRepository = Depends(get_warehouse_repo),
    location_repo: LocationRepository = Depends(get_location_repo),
):
    service = WarehouseService(warehouse_repo, location_repo)
    try:
        warehouse = await service.set_default_warehouse(company_id=ctx.company_id, warehouse_id=warehouse_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    await db.commit()
    return warehouse


@router.get("/warehouses", response_model=list[WarehouseOut])
async def list_warehouses(
    ctx: AuthContext = Depends(require_permission("inventory.warehouse.view")),
    warehouse_repo: WarehouseRepository = Depends(get_warehouse_repo),
):
    return await warehouse_repo.list_by_company(ctx.company_id)


@router.get("/warehouses/{warehouse_id}/locations", response_model=list[dict])
async def list_locations(
    warehouse_id: UUID,
    ctx: AuthContext = Depends(require_permission("inventory.warehouse.view")),
    location_repo: LocationRepository = Depends(get_location_repo),
):
    locations = await location_repo.list_by_warehouse(warehouse_id)
    return [{"id": str(loc.id), "name": loc.name, "is_virtual": loc.is_virtual} for loc in locations]


@router.post("/stock/receive", response_model=StockMoveOut, status_code=status.HTTP_201_CREATED)
async def receive_stock(
    payload: StockReceiveRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("inventory.stock.receive")),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
    layer_repo: StockLayerRepository = Depends(get_stock_layer_repo),
    move_repo: StockMoveRepository = Depends(get_stock_move_repo),
    valuation_method: str = Depends(get_company_valuation_method),
):
    service = InventoryValuationService(quant_repo, layer_repo, move_repo)
    try:
        move = await service.receive_stock(
            company_id=ctx.company_id,
            product_id=payload.product_id,
            location_id=payload.location_id,
            qty=payload.qty,
            unit_cost=payload.unit_cost,
            valuation_method=valuation_method,
            source_table="manual_receipt",
            source_id=payload.product_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return move


@router.get("/stock/quants", response_model=list[StockQuantOut])
async def list_stock_quants(
    ctx: AuthContext = Depends(require_permission("inventory.stock.view")),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
):
    return await quant_repo.list_by_company(ctx.company_id)


@router.get("/stock/moves", response_model=list[StockMoveOut])
async def list_stock_moves(
    product_id: UUID | None = None,
    ctx: AuthContext = Depends(require_permission("inventory.stock.view")),
    move_repo: StockMoveRepository = Depends(get_stock_move_repo),
):
    return await move_repo.list_by_company(ctx.company_id, product_id=product_id)


@router.get("/stock/cardex", response_model=ProductCardexResponse)
async def product_cardex(
    product_id: UUID,
    date_from: date,
    date_to: date,
    warehouse_id: UUID | None = None,
    source_table: str | None = None,
    ctx: AuthContext = Depends(require_permission("inventory.stock.view")),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
    layer_repo: StockLayerRepository = Depends(get_stock_layer_repo),
    move_repo: StockMoveRepository = Depends(get_stock_move_repo),
):
    """Bundle E — standard product cardex (Owner-requested): opening qty,
    every move in range with a running balance, closing qty. Optional
    warehouse and document-type (source_table) filters narrow the inquiry,
    matching how Accounting's General Ledger already filters by account."""
    service = InventoryValuationService(quant_repo, layer_repo, move_repo)
    result = await service.product_cardex(
        company_id=ctx.company_id,
        product_id=product_id,
        date_from=date_from,
        date_to=date_to,
        warehouse_id=warehouse_id,
        source_table=source_table,
    )
    return ProductCardexResponse(
        product_id=product_id,
        opening_qty=result["opening_qty"],
        closing_qty=result["closing_qty"],
        lines=[
            CardexLineOut(
                id=line["move"].id,
                moved_at=line["move"].moved_at,
                move_type=line["move"].move_type,
                source_table=line["move"].source_table,
                source_id=line["move"].source_id,
                qty=line["move"].qty,
                unit_cost=line["move"].unit_cost,
                signed_qty=line["signed_qty"],
                running_qty=line["running_qty"],
            )
            for line in result["lines"]
        ],
    )


@router.post("/transfers", response_model=list[StockMoveOut], status_code=status.HTTP_201_CREATED)
async def create_transfer(
    payload: TransferCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("inventory.transfer.create")),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
    layer_repo: StockLayerRepository = Depends(get_stock_layer_repo),
    move_repo: StockMoveRepository = Depends(get_stock_move_repo),
    valuation_method: str = Depends(get_company_valuation_method),
):
    """UC-INV-01 — a transfer is an issue at the source + a receipt at the
    destination, at the same cost (no valuation gain/loss on an internal
    move, per Phase 6 §5)."""
    service = InventoryValuationService(quant_repo, layer_repo, move_repo)
    try:
        import uuid as _uuid

        transfer_id = _uuid.uuid4()
        issue_move, cost = await service.issue_stock(
            company_id=ctx.company_id,
            product_id=payload.product_id,
            location_id=payload.source_location_id,
            qty=payload.qty,
            valuation_method=valuation_method,
            source_table="stock_transfer",
            source_id=transfer_id,
            move_type="transfer",
        )
        unit_cost = cost / payload.qty if payload.qty > 0 else 0
        receive_move = await service.receive_stock(
            company_id=ctx.company_id,
            product_id=payload.product_id,
            location_id=payload.dest_location_id,
            qty=payload.qty,
            unit_cost=unit_cost,
            valuation_method=valuation_method,
            source_table="stock_transfer",
            source_id=transfer_id,
        )
    except (ValueError, InsufficientStockError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return [issue_move, receive_move]


@router.get("/cycle-counts", response_model=list[CycleCountOut])
async def list_cycle_counts(
    ctx: AuthContext = Depends(require_permission("inventory.stock.view")),
    cycle_count_repo: CycleCountRepository = Depends(get_cycle_count_repo),
):
    return await cycle_count_repo.list_by_company(ctx.company_id)


@router.get("/cycle-counts/{cycle_count_id}", response_model=CycleCountDetailResponse)
async def get_cycle_count(
    cycle_count_id: UUID,
    ctx: AuthContext = Depends(require_permission("inventory.stock.view")),
    cycle_count_repo: CycleCountRepository = Depends(get_cycle_count_repo),
):
    cycle_count = await cycle_count_repo.get_by_id(cycle_count_id)
    if cycle_count is None or cycle_count.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cycle count not found")
    lines = await cycle_count_repo.get_lines(cycle_count_id)
    return CycleCountDetailResponse(cycle_count=cycle_count, lines=lines)


@router.post("/cycle-counts", response_model=CycleCountDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_cycle_count(
    payload: CycleCountCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("inventory.cycle_count.manage")),
    cycle_count_repo: CycleCountRepository = Depends(get_cycle_count_repo),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
):
    service = CycleCountService(cycle_count_repo, quant_repo)
    cycle_count = await service.create_cycle_count(
        company_id=ctx.company_id,
        warehouse_id=payload.warehouse_id,
        scheduled_date=payload.scheduled_date,
        lines=[line.model_dump() for line in payload.lines],
    )
    await db.commit()
    # Phase 17C-RLS: db.commit() ends the transaction set_company_context()
    # scoped its SET LOCAL to — the follow-up read needs it re-established,
    # or it runs with no valid RLS context on this pooled connection.
    await set_company_context(db, ctx.company_id)
    lines = await cycle_count_repo.get_lines(cycle_count.id)
    return CycleCountDetailResponse(cycle_count=cycle_count, lines=lines)


@router.post("/cycle-counts/{cycle_count_id}:approve", response_model=CycleCountDetailResponse)
async def approve_cycle_count(
    cycle_count_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("inventory.cycle_count.manage", require_branch=True)),
    cycle_count_repo: CycleCountRepository = Depends(get_cycle_count_repo),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
    layer_repo: StockLayerRepository = Depends(get_stock_layer_repo),
    move_repo: StockMoveRepository = Depends(get_stock_move_repo),
    account_repo: AccountRepository = Depends(get_account_repo),
    journal_repo: JournalRepository = Depends(get_journal_repo),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
    period_repo: FiscalPeriodRepository = Depends(get_fiscal_period_repo),
    valuation_method: str = Depends(get_company_valuation_method),
):
    """FR-INV-006: posts a Stock Move (and matching journal entry, FR-INV-005)
    for each line's discrepancy, then marks the count approved."""
    cycle_count = await cycle_count_repo.get_by_id(cycle_count_id)
    if cycle_count is None or cycle_count.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cycle count not found")
    if cycle_count.status == "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cycle count already approved")

    lines = await cycle_count_repo.get_lines(cycle_count_id)
    inv_service = InventoryValuationService(quant_repo, layer_repo, move_repo)
    journal_service = JournalEntryService(entry_repo, journal_repo, account_repo, period_repo)

    inventory_account = await account_repo.get_by_code(ctx.company_id, ACCOUNT_CODE_INVENTORY)
    adjustment_account = await account_repo.get_by_code(ctx.company_id, ACCOUNT_CODE_ADJUSTMENT)
    if not (inventory_account and adjustment_account):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Default Chart of Accounts is not seeded")

    # Each line still gets its own Stock Move (a physical quantity movement
    # is inherently per product/location — it cannot be "netted" across
    # different products), tagged move_type="adjustment" and
    # source_table="cycle_count_line" so it reads as a distinct document
    # type from ordinary receipts/transfers everywhere it's shown (Stock
    # Card, Moves tab). The accounting impact is different: rather than one
    # journal entry per line, every line's value change is accumulated into
    # a single net amount and posted as ONE journal entry for the whole
    # cycle count — the standard ERP treatment for a stocktake adjustment,
    # and what a reviewer actually wants to see in the ledger (one line
    # item to approve/audit, not N).
    net_value = Decimal("0")  # positive = net increase (Dr Inventory), negative = net decrease

    for line in lines:
        diff = line.counted_qty - line.system_qty
        if diff == 0:
            continue
        if diff > 0:
            move = await inv_service.receive_stock(
                company_id=ctx.company_id,
                product_id=line.product_id,
                location_id=line.location_id,
                qty=diff,
                unit_cost=(await quant_repo.get(line.product_id, line.location_id)).moving_avg_cost,
                valuation_method=valuation_method,
                source_table="cycle_count_line",
                source_id=line.id,
            )
            net_value += move.qty * move.unit_cost
        else:
            move, cost = await inv_service.issue_stock(
                company_id=ctx.company_id,
                product_id=line.product_id,
                location_id=line.location_id,
                qty=abs(diff),
                valuation_method=valuation_method,
                source_table="cycle_count_line",
                source_id=line.id,
                move_type="adjustment",
            )
            net_value -= cost

        line.stock_move_id = move.id

    if net_value > 0:
        entry_lines = [
            {"account_id": inventory_account.id, "debit": net_value, "credit": 0},
            {"account_id": adjustment_account.id, "debit": 0, "credit": net_value},
        ]
    elif net_value < 0:
        entry_lines = [
            {"account_id": adjustment_account.id, "debit": -net_value, "credit": 0},
            {"account_id": inventory_account.id, "debit": 0, "credit": -net_value},
        ]
    else:
        entry_lines = None

    if entry_lines is not None:
        entry = await journal_service.create_draft_entry(
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            journal_code="GEN",
            entry_date=cycle_count.scheduled_date,
            reference=f"Cycle count {cycle_count.id}",
            lines=entry_lines,
            created_by=ctx.user_id,
            source_table="cycle_count",
            source_id=cycle_count.id,
        )
        await journal_service.post_entry(entry_id=entry.id, company_id=ctx.company_id)

    cycle_count.status = "approved"
    await db.commit()
    # Phase 17C-RLS: same rationale as create_cycle_count above.
    await set_company_context(db, ctx.company_id)

    updated_lines = await cycle_count_repo.get_lines(cycle_count_id)
    return CycleCountDetailResponse(cycle_count=cycle_count, lines=updated_lines)
