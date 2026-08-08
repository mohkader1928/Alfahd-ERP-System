"""FastAPI routes for Purchasing, per Phase 10 §6.5."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.purchasing.api.deps import (
    get_company_valuation_method,
    get_goods_receipt_service,
    get_purchase_order_repo,
    get_purchase_order_service,
    get_vendor_bill_repo,
    get_vendor_bill_service,
    require_permission,
)
from src.modules.purchasing.api.schemas import (
    DebitNoteCreateRequest,
    GoodsReceiptCreateRequest,
    GoodsReceiptOut,
    PurchaseOrderCreateRequest,
    PurchaseOrderDetailResponse,
    PurchaseOrderOut,
    RejectPurchaseOrderRequest,
    VendorBillCreateRequest,
    VendorBillDetailResponse,
    VendorBillOut,
)
from src.modules.purchasing.application.services import (
    GoodsReceiptService,
    PurchaseOrderService,
    VendorBillService,
)
from src.modules.purchasing.domain.entities import ThreeWayMatchError
from src.modules.purchasing.infrastructure.repositories import (
    PurchaseOrderRepository,
    VendorBillRepository,
)
from src.shared.api.pagination import Page, PageParams
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext

router = APIRouter()


@router.get("/orders", response_model=Page[PurchaseOrderOut])
async def list_purchase_orders(
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page_params: PageParams = Depends(),
    ctx: AuthContext = Depends(require_permission("purchasing.order.view")),
    order_repo: PurchaseOrderRepository = Depends(get_purchase_order_repo),
):
    """List-view server-side filtering (Product Owner audit): real
    LIMIT/OFFSET + status/date filters, same pattern as Sales Invoices."""
    items, total = await order_repo.list_by_company_page(
        ctx.company_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        offset=page_params.offset,
        limit=page_params.page_size,
    )
    return Page(items=items, total=total, page=page_params.page, page_size=page_params.page_size)


@router.get("/vendor-bills", response_model=Page[VendorBillOut])
async def list_vendor_bills(
    partner_id: UUID | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page_params: PageParams = Depends(),
    ctx: AuthContext = Depends(require_permission("purchasing.vendor_bill.view")),
    bill_repo: VendorBillRepository = Depends(get_vendor_bill_repo),
):
    """List-view server-side filtering (Product Owner audit): real
    LIMIT/OFFSET + partner/status/date filters, same pattern as Sales
    Invoices."""
    items, total = await bill_repo.list_by_company_page(
        ctx.company_id,
        partner_id=partner_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        offset=page_params.offset,
        limit=page_params.page_size,
    )
    return Page(items=items, total=total, page=page_params.page, page_size=page_params.page_size)


@router.get("/vendor-bills/{bill_id}", response_model=VendorBillDetailResponse)
async def get_vendor_bill(
    bill_id: UUID,
    ctx: AuthContext = Depends(require_permission("purchasing.vendor_bill.view")),
    bill_repo: VendorBillRepository = Depends(get_vendor_bill_repo),
):
    bill = await bill_repo.get_by_id(bill_id)
    if bill is None or bill.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendor bill not found")
    lines = await bill_repo.get_lines(bill_id)
    return VendorBillDetailResponse(bill=bill, lines=lines)


@router.post("/orders", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(
    payload: PurchaseOrderCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("purchasing.order.create", require_branch=True)),
    service: PurchaseOrderService = Depends(get_purchase_order_service),
):
    try:
        order = await service.create_purchase_order(
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            partner_id=payload.partner_id,
            order_date=payload.order_date,
            lines=[line.model_dump() for line in payload.lines],
            created_by=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return order


@router.post("/orders/{order_id}:confirm", response_model=PurchaseOrderOut)
async def confirm_purchase_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("purchasing.order.confirm")),
    service: PurchaseOrderService = Depends(get_purchase_order_service),
):
    """Auto-confirms unless the company has set `po_approval_threshold` and
    this order's total exceeds it, in which case it routes to
    `pending_approval` (Approval Workflow) — see PurchaseOrderService."""
    try:
        order = await service.confirm_purchase_order(order_id=order_id, company_id=ctx.company_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return order


@router.post("/orders/{order_id}:approve", response_model=PurchaseOrderOut)
async def approve_purchase_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("purchasing.order.approve")),
    service: PurchaseOrderService = Depends(get_purchase_order_service),
):
    try:
        order = await service.approve_purchase_order(order_id=order_id, company_id=ctx.company_id, approved_by=ctx.user_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return order


@router.post("/orders/{order_id}:reject", response_model=PurchaseOrderOut)
async def reject_purchase_order(
    order_id: UUID,
    payload: RejectPurchaseOrderRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("purchasing.order.approve")),
    service: PurchaseOrderService = Depends(get_purchase_order_service),
):
    try:
        order = await service.reject_purchase_order(
            order_id=order_id, company_id=ctx.company_id, rejected_by=ctx.user_id, reason=payload.reason
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return order


@router.get("/orders/{order_id}", response_model=PurchaseOrderDetailResponse)
async def get_purchase_order(
    order_id: UUID,
    ctx: AuthContext = Depends(require_permission("purchasing.order.view")),
    order_repo: PurchaseOrderRepository = Depends(get_purchase_order_repo),
):
    order = await order_repo.get_by_id(order_id)
    if order is None or order.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase order not found")
    lines = await order_repo.get_lines(order_id)
    return PurchaseOrderDetailResponse(order=order, lines=lines)


@router.post(
    "/orders/{order_id}/goods-receipts", response_model=GoodsReceiptOut, status_code=status.HTTP_201_CREATED
)
async def record_goods_receipt(
    order_id: UUID,
    payload: GoodsReceiptCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("purchasing.goods_receipt.create", require_branch=True)),
    service: GoodsReceiptService = Depends(get_goods_receipt_service),
    valuation_method: str = Depends(get_company_valuation_method),
):
    try:
        receipt = await service.record_receipt(
            purchase_order_id=order_id,
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            created_by=ctx.user_id,
            valuation_method=valuation_method,
            lines=[line.model_dump() for line in payload.lines],
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return receipt


@router.post("/orders/{order_id}/vendor-bills", response_model=VendorBillOut, status_code=status.HTTP_201_CREATED)
async def register_vendor_bill(
    order_id: UUID,
    payload: VendorBillCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("purchasing.vendor_bill.create", require_branch=True)),
    service: VendorBillService = Depends(get_vendor_bill_service),
):
    try:
        bill = await service.register_bill(
            purchase_order_id=order_id,
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            vendor_reference=payload.vendor_reference,
            lines=[line.model_dump() for line in payload.lines],
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return bill


@router.post(
    "/vendor-bills/{bill_id}:debit-note", response_model=VendorBillOut, status_code=status.HTTP_201_CREATED
)
async def issue_debit_note(
    bill_id: UUID,
    payload: DebitNoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("purchasing.vendor_bill.debit_note", require_branch=True)),
    service: VendorBillService = Depends(get_vendor_bill_service),
):
    try:
        debit_note = await service.issue_debit_note(
            original_bill_id=bill_id,
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            created_by=ctx.user_id,
            reason=payload.reason,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return debit_note


@router.post("/vendor-bills/{bill_id}:approve", response_model=VendorBillOut)
async def approve_vendor_bill(
    bill_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("purchasing.vendor_bill.approve")),
    service: VendorBillService = Depends(get_vendor_bill_service),
):
    try:
        bill = await service.approve_and_post(bill_id=bill_id, company_id=ctx.company_id, created_by=ctx.user_id)
    except ThreeWayMatchError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return bill
