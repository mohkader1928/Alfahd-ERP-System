"""FastAPI dependencies for Sales."""

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
    PartnerRepository,
    ProductRepository,
)
from src.modules.inventory.application.services import InventoryValuationService
from src.modules.inventory.infrastructure.repositories import (
    LocationRepository,
    StockLayerRepository,
    StockMoveRepository,
    StockQuantRepository,
    WarehouseRepository,
)
from src.modules.sales.application.services import QuotationService, SalesInvoiceService
from src.modules.sales.infrastructure.repositories import (
    QuotationRepository,
    SalesInvoiceRepository,
    SalesOrderRepository,
    ZatcaSubmissionRepository,
)
from src.modules.zatca.application.zatca_service import ZatcaInvoiceProcessor
from src.modules.zatca.infrastructure.gateways.sandbox_gateway import SandboxZatcaGateway
from src.modules.zatca.infrastructure.signing import DevSigningService
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext, get_auth_context


def get_quotation_repo(db: AsyncSession = Depends(get_db)) -> QuotationRepository:
    return QuotationRepository(db)


def get_sales_order_repo(db: AsyncSession = Depends(get_db)) -> SalesOrderRepository:
    return SalesOrderRepository(db)


def get_sales_invoice_repo(db: AsyncSession = Depends(get_db)) -> SalesInvoiceRepository:
    return SalesInvoiceRepository(db)


def get_zatca_submission_repo(db: AsyncSession = Depends(get_db)) -> ZatcaSubmissionRepository:
    return ZatcaSubmissionRepository(db)


def get_quotation_service(
    quotation_repo: QuotationRepository = Depends(get_quotation_repo),
    order_repo: SalesOrderRepository = Depends(get_sales_order_repo),
) -> QuotationService:
    return QuotationService(quotation_repo, order_repo)


async def get_sales_invoice_service(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    invoice_repo: SalesInvoiceRepository = Depends(get_sales_invoice_repo),
    order_repo: SalesOrderRepository = Depends(get_sales_order_repo),
    zatca_submission_repo: ZatcaSubmissionRepository = Depends(get_zatca_submission_repo),
) -> SalesInvoiceService:
    company_repo = CompanyRepository(db)
    company = await company_repo.get_by_id(ctx.company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    partner_repo = PartnerRepository(db)
    product_repo = ProductRepository(db)
    account_repo = AccountRepository(db)
    journal_entry_service = JournalEntryService(
        JournalEntryRepository(db), JournalRepository(db), AccountRepository(db), FiscalPeriodRepository(db)
    )
    zatca_processor = ZatcaInvoiceProcessor(gateway=SandboxZatcaGateway(), signing_service=DevSigningService())

    inventory_service = InventoryValuationService(
        StockQuantRepository(db), StockLayerRepository(db), StockMoveRepository(db)
    )
    warehouse_repo = WarehouseRepository(db)
    location_repo = LocationRepository(db)

    return SalesInvoiceService(
        invoice_repo=invoice_repo,
        order_repo=order_repo,
        zatca_submission_repo=zatca_submission_repo,
        partner_repo=partner_repo,
        product_repo=product_repo,
        account_repo=account_repo,
        journal_entry_service=journal_entry_service,
        zatca_processor=zatca_processor,
        seller_name=company.legal_name,
        seller_vat_number=company.vat_number,
        inventory_service=inventory_service,
        warehouse_repo=warehouse_repo,
        location_repo=location_repo,
        valuation_method=company.valuation_method,
    )
