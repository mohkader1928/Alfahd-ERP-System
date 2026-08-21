"""FastAPI routes for Inventory, per Phase 10 §6.5 (nucleus scope: no
Goods Receipt yet — M4 will wire Purchasing's receipt into
`InventoryValuationService.receive_stock`; `/stock/receive` is a direct
stand-in used for initial stock entry until then)."""

from datetime import date
from decimal import Decimal
from typing import Literal
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
from src.modules.identity.api.deps import get_company_repo, get_product_repo
from src.modules.identity.infrastructure.repositories import CompanyRepository, ProductRepository
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
from src.modules.purchasing.infrastructure.repositories import GoodsReceiptRepository, VendorBillRepository
from src.modules.sales.infrastructure.repositories import SalesInvoiceRepository
from src.modules.inventory.api.schemas import (
    CardexLineOut,
    CycleCountCreateRequest,
    CycleCountDetailResponse,
    CycleCountOut,
    LowStockRowOut,
    ProductCardexResponse,
    StockBalanceByProductOut,
    StockBalanceByWarehouseOut,
    StockBalanceOut,
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
from src.shared.reporting.company_name import resolve_company_name
from src.shared.reporting.export_render import ReportColumn, ReportTable
from src.shared.reporting.export_response import build_export_response
from src.shared.reporting.formatting import format_amount, format_date_str, format_qty
from src.shared.reporting.labels import label, title
from src.shared.security.auth_context import AuthContext

ExportFormatParam = Literal["json", "pdf", "xlsx"]

router = APIRouter()

ACCOUNT_CODE_INVENTORY = "1300"
ACCOUNT_CODE_ADJUSTMENT = "5200"
ACCOUNT_CODE_INVENTORY_VARIANCE = "5150"


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
        # Manual receive posts no journal entry at all today (see this
        # module's own docstring), so there is no GL to keep a valuation
        # variance reconciled against here -- discard it, same as any
        # other GL-neutral path.
        move, _variance = await service.receive_stock(
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


@router.get("/stock/balance", response_model=StockBalanceOut)
async def get_stock_balance(
    product_id: UUID,
    warehouse_id: UUID,
    ctx: AuthContext = Depends(require_permission("inventory.stock.view")),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
):
    """Owner request: the on-hand balance a Quotation/Sales Order/Purchase
    Order/Transfer line shows next to a product, scoped to that
    document's own warehouse — one lightweight lookup per product+
    warehouse pairing rather than shipping the whole `/stock/quants` list
    to every document-editing screen."""
    qty = await quant_repo.qty_on_hand_for_product_in_warehouse(ctx.company_id, product_id, warehouse_id)
    return StockBalanceOut(product_id=product_id, warehouse_id=warehouse_id, qty_on_hand=qty)


@router.get("/stock/balance-by-product", response_model=StockBalanceByProductOut)
async def get_stock_balance_by_product(
    product_id: UUID,
    ctx: AuthContext = Depends(require_permission("inventory.stock.view")),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
    warehouse_repo: WarehouseRepository = Depends(get_warehouse_repo),
):
    """Owner request: a single product's balance across every warehouse
    at once (unlike /stock/balance, which is scoped to one warehouse),
    with the grand total across all of them -- every warehouse the
    company has is listed, even ones this product currently has zero
    stock in, so the report reads as complete rather than silently
    omitting rows."""
    warehouses = await warehouse_repo.list_by_company(ctx.company_id)
    qty_by_warehouse = await quant_repo.qty_on_hand_by_warehouse_for_product(ctx.company_id, product_id)
    by_warehouse = sorted(
        (
            StockBalanceByWarehouseOut(
                warehouse_id=w.id,
                warehouse_name=w.name,
                qty_on_hand=qty_by_warehouse.get(w.id, Decimal("0.000000")),
            )
            for w in warehouses
        ),
        key=lambda row: row.warehouse_name,
    )
    total_qty_on_hand = sum((row.qty_on_hand for row in by_warehouse), Decimal("0"))
    return StockBalanceByProductOut(
        product_id=product_id, total_qty_on_hand=total_qty_on_hand, by_warehouse=by_warehouse
    )


@router.get("/stock/low-stock", response_model=list[LowStockRowOut])
async def list_low_stock(
    ctx: AuthContext = Depends(require_permission("inventory.stock.view")),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
    product_repo: ProductRepository = Depends(get_product_repo),
):
    """Table-stakes in every reference ERP (SAP B1, Dynamics 365 BC, Odoo):
    which products are at or below their reorder point right now, across
    every warehouse/location combined — a product-level threshold, not a
    per-location one. Only products with a reorder_point actually
    configured are candidates; everything else has no threshold to
    compare against."""
    candidates = await product_repo.list_with_reorder_point(ctx.company_id)
    qty_by_product = await quant_repo.qty_on_hand_by_product(ctx.company_id)

    rows = []
    for product in candidates:
        qty_on_hand = qty_by_product.get(product.id, Decimal("0"))
        if qty_on_hand <= product.reorder_point:
            rows.append(
                LowStockRowOut(
                    product_id=product.id,
                    sku=product.sku,
                    name=product.name,
                    name_ar=product.name_ar,
                    qty_on_hand=qty_on_hand,
                    reorder_point=product.reorder_point,
                    shortfall=product.reorder_point - qty_on_hand,
                )
            )
    rows.sort(key=lambda r: r.shortfall, reverse=True)
    return rows


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
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("inventory.stock.view")),
    quant_repo: StockQuantRepository = Depends(get_stock_quant_repo),
    layer_repo: StockLayerRepository = Depends(get_stock_layer_repo),
    move_repo: StockMoveRepository = Depends(get_stock_move_repo),
    location_repo: LocationRepository = Depends(get_location_repo),
    product_repo: ProductRepository = Depends(get_product_repo),
    company_repo: CompanyRepository = Depends(get_company_repo),
    db: AsyncSession = Depends(get_db),
):
    """Bundle E — standard product cardex (Owner-requested): opening qty,
    every move in range with a running balance, closing qty. Optional
    warehouse and document-type (source_table) filters narrow the inquiry,
    matching how Accounting's General Ledger already filters by account.
    Each line also carries the source document's own number and the
    warehouse it touched (Owner request), resolved via the owning
    module's own repository classes constructed directly off this
    request's session -- deliberately NOT via Sales/Purchasing's own
    `api.deps` providers, since those modules' deps.py files themselves
    import back into Inventory (for GL-posting orchestration), and
    importing them here at module load time creates a circular import
    that only "resolves" by accident of whichever module the app happens
    to import first."""
    sales_invoice_repo = SalesInvoiceRepository(db)
    vendor_bill_repo = VendorBillRepository(db)
    goods_receipt_repo = GoodsReceiptRepository(db)
    service = InventoryValuationService(quant_repo, layer_repo, move_repo, location_repo=location_repo)
    result = await service.product_cardex(
        company_id=ctx.company_id,
        product_id=product_id,
        date_from=date_from,
        date_to=date_to,
        warehouse_id=warehouse_id,
        source_table=source_table,
    )
    document_numbers = await _resolve_cardex_document_numbers(
        result["lines"], sales_invoice_repo, vendor_bill_repo, goods_receipt_repo
    )
    if format == "json":
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
                    document_number=document_numbers.get(line["move"].source_id),
                    warehouse_id=line["warehouse_id"],
                    warehouse_name=line["warehouse_name"],
                    qty=line["move"].qty,
                    unit_cost=line["move"].unit_cost,
                    signed_qty=line["signed_qty"],
                    running_qty=line["running_qty"],
                )
                for line in result["lines"]
            ],
        )

    product = await product_repo.get_by_id(product_id)
    product_name = (product.name_ar if lang == "ar" and product.name_ar else product.name) if product else str(product_id)
    table_rows = [
        [
            format_date_str(line["move"].moved_at),
            line["move"].move_type,
            line["move"].source_table,
            document_numbers.get(line["move"].source_id) or "",
            line["warehouse_name"] or "",
            format_qty(line["signed_qty"]),
            format_amount(line["move"].unit_cost),
            format_qty(line["running_qty"]),
        ]
        for line in result["lines"]
    ]
    table = ReportTable(
        title=f'{title(lang, "product_cardex")} — {product_name}',
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f"{date_from} — {date_to}",
        columns=[
            ReportColumn(label(lang, "date")),
            ReportColumn(label(lang, "type")),
            ReportColumn(label(lang, "source")),
            ReportColumn(label(lang, "number")),
            ReportColumn(label(lang, "warehouse")),
            ReportColumn(label(lang, "qty"), "end"),
            ReportColumn(label(lang, "unit_cost"), "end"),
            ReportColumn(label(lang, "running_qty"), "end"),
        ],
        rows=[
            ["", "", label(lang, "opening_balance"), "", "", "", "", format_qty(result["opening_qty"])],
            *table_rows,
        ],
        totals=["", "", label(lang, "closing_balance"), "", "", "", "", format_qty(result["closing_qty"])],
        rtl=lang == "ar",
    )
    return build_export_response(format, f"product-cardex-{product_name}", table)


async def _resolve_cardex_document_numbers(
    lines: list[dict],
    sales_invoice_repo: SalesInvoiceRepository,
    vendor_bill_repo: VendorBillRepository,
    goods_receipt_repo: GoodsReceiptRepository,
) -> dict[UUID, str]:
    """Owner request (Product Cardex detail): resolve each line's
    `source_id` to a human-readable document number. Only the source
    tables that actually back a real numbered document resolve to
    anything -- cycle_count_line/manual_receipt/stock_transfer have no
    document number anywhere in the schema, so those lines simply show
    none (frontend falls back to the type label alone), same as
    `sourceDocumentHref` already has no entry for them."""
    ids_by_table: dict[str, set[UUID]] = {}
    for line in lines:
        move = line["move"]
        ids_by_table.setdefault(move.source_table, set()).add(move.source_id)

    numbers: dict[UUID, str] = {}
    if "sales_invoice" in ids_by_table:
        numbers.update(await sales_invoice_repo.numbers_for_ids(list(ids_by_table["sales_invoice"])))
    if "vendor_bill" in ids_by_table:
        numbers.update(await vendor_bill_repo.numbers_for_ids(list(ids_by_table["vendor_bill"])))
    if "goods_receipt_line" in ids_by_table:
        numbers.update(await goods_receipt_repo.numbers_for_lines(list(ids_by_table["goods_receipt_line"])))
    return numbers


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
        # A transfer posts no journal entry at all (same account both legs
        # would touch -- see this endpoint's own docstring), so there is
        # no GL to keep a valuation variance reconciled against -- discard
        # it, same as manual receive above.
        receive_move, _variance = await service.receive_stock(
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
    net_valuation_variance = Decimal("0")

    for line in lines:
        diff = line.counted_qty - line.system_qty
        if diff == 0:
            continue
        if diff > 0:
            move, variance = await inv_service.receive_stock(
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
            net_valuation_variance += variance
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

    if net_valuation_variance != 0:
        # Owner-reported bug: a count that brings a negative position
        # (oversold via FR-INV-007) to EXACTLY zero can't carry its true
        # blended value in a qty*avg register -- see
        # `InventoryValuationService.receive_stock`'s own comment. Posted
        # explicitly instead of letting the register silently drift from
        # the GL.
        variance_account = await account_repo.get_by_code(ctx.company_id, ACCOUNT_CODE_INVENTORY_VARIANCE)
        if variance_account is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Default Chart of Accounts is not seeded")
        amount = abs(net_valuation_variance)
        variance_lines = (
            [
                {"account_id": inventory_account.id, "debit": 0, "credit": amount},
                {"account_id": variance_account.id, "debit": amount, "credit": 0},
            ]
            if net_valuation_variance > 0
            else [
                {"account_id": inventory_account.id, "debit": amount, "credit": 0},
                {"account_id": variance_account.id, "debit": 0, "credit": amount},
            ]
        )
        variance_entry = await journal_service.create_draft_entry(
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            journal_code="GEN",
            entry_date=cycle_count.scheduled_date,
            reference=f"Inventory valuation variance for cycle count {cycle_count.id}",
            lines=variance_lines,
            created_by=ctx.user_id,
            source_table="cycle_count",
            source_id=cycle_count.id,
        )
        await journal_service.post_entry(entry_id=variance_entry.id, company_id=ctx.company_id)

    cycle_count.status = "approved"
    await db.commit()
    # Phase 17C-RLS: same rationale as create_cycle_count above.
    await set_company_context(db, ctx.company_id)

    updated_lines = await cycle_count_repo.get_lines(cycle_count_id)
    return CycleCountDetailResponse(cycle_count=cycle_count, lines=updated_lines)
