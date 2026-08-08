"""FastAPI dependencies for Purchasing."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.application.services import JournalEntryService
from src.modules.accounting.infrastructure.repositories import (
    AccountRepository,
    FiscalPeriodRepository,
    JournalEntryRepository,
    JournalRepository,
)
from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.modules.identity.infrastructure.repositories import (
    CompanyRepository,
    ProductRepository,
    RoleRepository,
)
from src.modules.inventory.application.services import InventoryValuationService
from src.modules.inventory.infrastructure.repositories import (
    LocationRepository,
    StockLayerRepository,
    StockMoveRepository,
    StockQuantRepository,
    WarehouseRepository,
)
from src.modules.notifications.infrastructure.repositories import NotificationRepository
from src.modules.purchasing.application.services import (
    GoodsReceiptService,
    PurchaseOrderService,
    VendorBillService,
)
from src.modules.purchasing.infrastructure.repositories import (
    GoodsReceiptRepository,
    PurchaseOrderRepository,
    VendorBillRepository,
)
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext, get_auth_context


def get_purchase_order_repo(db: AsyncSession = Depends(get_db)) -> PurchaseOrderRepository:
    return PurchaseOrderRepository(db)


def get_goods_receipt_repo(db: AsyncSession = Depends(get_db)) -> GoodsReceiptRepository:
    return GoodsReceiptRepository(db)


def get_vendor_bill_repo(db: AsyncSession = Depends(get_db)) -> VendorBillRepository:
    return VendorBillRepository(db)


def get_purchase_order_service(
    db: AsyncSession = Depends(get_db),
    order_repo: PurchaseOrderRepository = Depends(get_purchase_order_repo),
) -> PurchaseOrderService:
    return PurchaseOrderService(
        order_repo,
        company_repo=CompanyRepository(db),
        role_repo=RoleRepository(db),
        notification_repo=NotificationRepository(db),
        product_repo=ProductRepository(db),
    )


async def get_goods_receipt_service(
    db: AsyncSession = Depends(get_db),
    receipt_repo: GoodsReceiptRepository = Depends(get_goods_receipt_repo),
    order_repo: PurchaseOrderRepository = Depends(get_purchase_order_repo),
) -> GoodsReceiptService:
    product_repo = ProductRepository(db)
    account_repo = AccountRepository(db)
    journal_entry_service = JournalEntryService(
        JournalEntryRepository(db), JournalRepository(db), AccountRepository(db), FiscalPeriodRepository(db)
    )
    inventory_service = InventoryValuationService(
        StockQuantRepository(db), StockLayerRepository(db), StockMoveRepository(db)
    )
    return GoodsReceiptService(
        receipt_repo=receipt_repo,
        order_repo=order_repo,
        product_repo=product_repo,
        account_repo=account_repo,
        journal_entry_service=journal_entry_service,
        inventory_service=inventory_service,
        warehouse_repo=WarehouseRepository(db),
        location_repo=LocationRepository(db),
    )


async def get_vendor_bill_service(
    db: AsyncSession = Depends(get_db),
    bill_repo: VendorBillRepository = Depends(get_vendor_bill_repo),
    order_repo: PurchaseOrderRepository = Depends(get_purchase_order_repo),
    receipt_repo: GoodsReceiptRepository = Depends(get_goods_receipt_repo),
) -> VendorBillService:
    product_repo = ProductRepository(db)
    account_repo = AccountRepository(db)
    journal_entry_service = JournalEntryService(
        JournalEntryRepository(db), JournalRepository(db), AccountRepository(db), FiscalPeriodRepository(db)
    )
    return VendorBillService(
        bill_repo=bill_repo,
        order_repo=order_repo,
        receipt_repo=receipt_repo,
        product_repo=product_repo,
        account_repo=account_repo,
        journal_entry_service=journal_entry_service,
    )


async def get_company_valuation_method(
    db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context)
) -> str:
    company = await CompanyRepository(db).get_by_id(ctx.company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company.valuation_method
