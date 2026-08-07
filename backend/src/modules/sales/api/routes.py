"""FastAPI routes for Sales, per Phase 10 §6.3."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.inventory.domain.entities import InsufficientStockError
from src.modules.sales.api.deps import (
    get_mailer,
    get_quotation_repo,
    get_quotation_service,
    get_sales_invoice_repo,
    get_sales_invoice_service,
    get_sales_order_repo,
    get_zatca_submission_repo,
    require_permission,
)
from src.modules.sales.api.schemas import (
    CreditNoteCreateRequest,
    InvoiceIssueResponse,
    QuotationCreateRequest,
    QuotationOut,
    SalesInvoiceOut,
    SalesOrderOut,
    SendInvoiceEmailRequest,
)
from src.modules.sales.application.services import QuotationService, SalesInvoiceService
from src.modules.sales.infrastructure.repositories import (
    QuotationRepository,
    SalesInvoiceRepository,
    SalesOrderRepository,
    ZatcaSubmissionRepository,
)
from src.shared.email.mailer import EmailNotConfiguredError
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext

router = APIRouter()


@router.get("/quotations", response_model=list[QuotationOut])
async def list_quotations(
    ctx: AuthContext = Depends(require_permission("sales.quotation.create")),
    quotation_repo: QuotationRepository = Depends(get_quotation_repo),
):
    return await quotation_repo.list_by_company(ctx.company_id)


@router.post("/quotations", response_model=QuotationOut, status_code=status.HTTP_201_CREATED)
async def create_quotation(
    payload: QuotationCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("sales.quotation.create", require_branch=True)),
    service: QuotationService = Depends(get_quotation_service),
):
    try:
        quotation = await service.create_quotation(
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            partner_id=payload.partner_id,
            quote_date=payload.quote_date,
            lines=[line.model_dump() for line in payload.lines],
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return quotation


@router.post("/quotations/{quotation_id}:confirm", response_model=SalesOrderOut)
async def confirm_quotation(
    quotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("sales.quotation.confirm")),
    service: QuotationService = Depends(get_quotation_service),
):
    try:
        order = await service.confirm_to_sales_order(quotation_id=quotation_id, company_id=ctx.company_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return order


@router.get("/orders", response_model=list[SalesOrderOut])
async def list_sales_orders(
    ctx: AuthContext = Depends(require_permission("sales.order.view")),
    order_repo: SalesOrderRepository = Depends(get_sales_order_repo),
):
    return await order_repo.list_by_company(ctx.company_id)


@router.get("/orders/{order_id}", response_model=SalesOrderOut)
async def get_sales_order(
    order_id: UUID,
    ctx: AuthContext = Depends(require_permission("sales.order.view")),
    order_repo: SalesOrderRepository = Depends(get_sales_order_repo),
):
    order = await order_repo.get_by_id(order_id)
    if order is None or order.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sales order not found")
    return order


@router.post("/orders/{order_id}:invoice", response_model=InvoiceIssueResponse, status_code=status.HTTP_201_CREATED)
async def issue_invoice(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("sales.invoice.create", require_branch=True)),
    service: SalesInvoiceService = Depends(get_sales_invoice_service),
):
    try:
        invoice, submission = await service.issue_invoice_from_order(
            sales_order_id=order_id, company_id=ctx.company_id, branch_id=ctx.branch_id, created_by=ctx.user_id
        )
    except (ValueError, InsufficientStockError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()

    if submission.status == "pending_submission":
        # FR-ZATCA-007: enqueue the async Reporting call (Celery worker,
        # see workers/tasks/zatca_tasks.py). Enqueued after commit so the
        # worker never picks up a row from an uncommitted transaction.
        from src.workers.tasks.zatca_tasks import report_invoice_task

        report_invoice_task.delay(str(invoice.id), company_id=str(ctx.company_id), tenant_id=str(ctx.tenant_id))

    return InvoiceIssueResponse(invoice=invoice, zatca_submission=submission)


@router.post(
    "/invoices/{invoice_id}:credit-note", response_model=InvoiceIssueResponse, status_code=status.HTTP_201_CREATED
)
async def issue_credit_note(
    invoice_id: UUID,
    payload: CreditNoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("sales.invoice.credit_note", require_branch=True)),
    service: SalesInvoiceService = Depends(get_sales_invoice_service),
):
    try:
        credit_note, submission = await service.issue_credit_note(
            original_invoice_id=invoice_id,
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            created_by=ctx.user_id,
            reason=payload.reason,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()

    if submission.status == "pending_submission":
        from src.workers.tasks.zatca_tasks import report_invoice_task

        report_invoice_task.delay(str(credit_note.id), company_id=str(ctx.company_id), tenant_id=str(ctx.tenant_id))

    return InvoiceIssueResponse(invoice=credit_note, zatca_submission=submission)


@router.get("/invoices", response_model=list[SalesInvoiceOut])
async def list_invoices(
    partner_id: UUID | None = None,
    ctx: AuthContext = Depends(require_permission("sales.invoice.create")),
    invoice_repo: SalesInvoiceRepository = Depends(get_sales_invoice_repo),
):
    return await invoice_repo.list_by_company(ctx.company_id, partner_id=partner_id)


@router.get("/invoices/{invoice_id}", response_model=InvoiceIssueResponse)
async def get_invoice(
    invoice_id: UUID,
    ctx: AuthContext = Depends(require_permission("sales.invoice.create")),
    invoice_repo: SalesInvoiceRepository = Depends(get_sales_invoice_repo),
    zatca_submission_repo: ZatcaSubmissionRepository = Depends(get_zatca_submission_repo),
):
    invoice = await invoice_repo.get_by_id(invoice_id)
    if invoice is None or invoice.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    submission = await zatca_submission_repo.get_by_invoice_id(invoice_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ZATCA submission not found for this invoice")
    return InvoiceIssueResponse(invoice=invoice, zatca_submission=submission)


@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: UUID,
    lang: str = "ar",
    ctx: AuthContext = Depends(require_permission("sales.invoice.create")),
    service: SalesInvoiceService = Depends(get_sales_invoice_service),
):
    try:
        pdf_bytes = await service.build_invoice_pdf(invoice_id=invoice_id, company_id=ctx.company_id, lang=lang)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=invoice.pdf"},
    )


@router.post("/invoices/{invoice_id}:send-email", response_model=SalesInvoiceOut)
async def send_invoice_email(
    invoice_id: UUID,
    payload: SendInvoiceEmailRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("sales.invoice.send_email")),
    service: SalesInvoiceService = Depends(get_sales_invoice_service),
    mailer=Depends(get_mailer),
):
    try:
        invoice = await service.send_invoice_email(
            invoice_id=invoice_id, company_id=ctx.company_id, to_email=payload.to_email, mailer=mailer
        )
    except (EmailNotConfiguredError, ValueError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return invoice


@router.get("/quotations/{quotation_id}", response_model=QuotationOut)
async def get_quotation(
    quotation_id: UUID,
    ctx: AuthContext = Depends(require_permission("sales.quotation.create")),
    quotation_repo: QuotationRepository = Depends(get_quotation_repo),
):
    quotation = await quotation_repo.get_by_id(quotation_id)
    if quotation is None or quotation.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    return quotation
