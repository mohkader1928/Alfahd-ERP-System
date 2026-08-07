"""FastAPI routes for Payments, per Phase 17D."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.api.deps import get_company_repo
from src.modules.identity.infrastructure.repositories import CompanyRepository, PartnerRepository
from src.modules.payments.api.deps import (
    get_partner_repo,
    get_payment_repo,
    get_payment_service,
    get_subledger_service,
    require_permission,
)
from src.modules.payments.api.schemas import (
    AgingResponse,
    DocumentBalanceOut,
    PaymentCreateRequest,
    PaymentDetailResponse,
    PaymentOut,
    SubledgerResponse,
)
from src.modules.payments.application.services import PaymentService, SubledgerService
from src.modules.payments.domain.entities import InvalidAllocationTargetError, OverAllocationError
from src.modules.payments.infrastructure.repositories import PaymentRepository
from src.shared.infrastructure.db.session import get_db
from src.shared.reporting.company_name import resolve_company_name
from src.shared.reporting.export_render import ReportColumn, ReportTable
from src.shared.reporting.export_response import build_export_response
from src.shared.reporting.formatting import format_amount, format_date_str
from src.shared.reporting.labels import label, title
from src.shared.security.auth_context import AuthContext

router = APIRouter()

ExportFormatParam = Literal["json", "pdf", "xlsx"]


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    payment_type: str | None = None,
    ctx: AuthContext = Depends(require_permission("payment.view")),
    payment_repo: PaymentRepository = Depends(get_payment_repo),
):
    return await payment_repo.list_by_company(ctx.company_id, payment_type=payment_type)


@router.get("/payments/{payment_id}", response_model=PaymentDetailResponse)
async def get_payment(
    payment_id: UUID,
    ctx: AuthContext = Depends(require_permission("payment.view")),
    payment_repo: PaymentRepository = Depends(get_payment_repo),
):
    payment = await payment_repo.get_by_id(payment_id)
    if payment is None or payment.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    allocations = await payment_repo.get_allocations(payment_id)
    return PaymentDetailResponse(payment=payment, allocations=allocations)


@router.get("/balance/sales-invoice/{invoice_id}", response_model=DocumentBalanceOut)
async def get_sales_invoice_balance(
    invoice_id: UUID,
    ctx: AuthContext = Depends(require_permission("payment.view")),
    service: PaymentService = Depends(get_payment_service),
):
    balance = await service.get_sales_invoice_balance(ctx.company_id, invoice_id)
    if balance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sales invoice not found")
    return balance


@router.get("/balance/vendor-bill/{bill_id}", response_model=DocumentBalanceOut)
async def get_vendor_bill_balance(
    bill_id: UUID,
    ctx: AuthContext = Depends(require_permission("payment.view")),
    service: PaymentService = Depends(get_payment_service),
):
    balance = await service.get_vendor_bill_balance(ctx.company_id, bill_id)
    if balance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendor bill not found")
    return balance


def _subledger_table(
    *, report_key: str, partner_name: str, company_name: str, date_from: date, date_to: date,
    result: dict, lang: str,
) -> ReportTable:
    rows = [
        [
            format_date_str(line["date"]),
            line["movement_type"],
            line["reference"],
            format_amount(line["debit"]),
            format_amount(line["credit"]),
            format_amount(line["running_balance"]),
        ]
        for line in result["lines"]
    ]
    return ReportTable(
        title=f'{title(lang, report_key)} — {partner_name}',
        company_name=company_name,
        subtitle=f"{date_from} — {date_to}",
        columns=[
            ReportColumn(label(lang, "date")),
            ReportColumn(label(lang, "type")),
            ReportColumn(label(lang, "reference")),
            ReportColumn(label(lang, "debit"), "end"),
            ReportColumn(label(lang, "credit"), "end"),
            ReportColumn(label(lang, "balance"), "end"),
        ],
        rows=[
            ["", "", label(lang, "opening_balance"), "", "", format_amount(result["opening_balance"])],
            *rows,
        ],
        totals=["", "", label(lang, "closing_balance"), "", "", format_amount(result["closing_balance"])],
        rtl=lang == "ar",
    )


def _aging_table(*, report_key: str, company_name: str, as_of_date: date, rows: list, lang: str) -> ReportTable:
    partner_label = label(lang, "customer") if report_key == "ar_aging" else label(lang, "vendor")
    table_rows = [
        [
            r["partner_name"],
            r["number"],
            format_date_str(r["due_date"]),
            format_amount(r["balance_due"]),
            str(r["days_overdue"]),
            r["bucket"],
        ]
        for r in rows
    ]
    total_due = sum((r["balance_due"] for r in rows), start=Decimal("0"))
    return ReportTable(
        title=title(lang, report_key),
        company_name=company_name,
        subtitle=f'{label(lang, "date")}: {as_of_date}',
        columns=[
            ReportColumn(partner_label),
            ReportColumn(label(lang, "reference")),
            ReportColumn(label(lang, "date")),
            ReportColumn(label(lang, "balance"), "end"),
            ReportColumn(label(lang, "days_overdue"), "end"),
            ReportColumn(label(lang, "bucket")),
        ],
        rows=table_rows,
        totals=[label(lang, "total"), "", "", format_amount(total_due), "", ""],
        rtl=lang == "ar",
    )


@router.get("/subledger/customer/{partner_id}", response_model=SubledgerResponse)
async def customer_subledger(
    partner_id: UUID,
    date_from: date,
    date_to: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("payment.subledger.view")),
    service: SubledgerService = Depends(get_subledger_service),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    partner = await partner_repo.get_by_id(partner_id)
    if partner is None or partner.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    result = await service.customer_subledger(
        company_id=ctx.company_id, partner_id=partner_id, date_from=date_from, date_to=date_to
    )
    if format == "json":
        return SubledgerResponse(
            partner_id=partner.id, partner_name=partner.name, date_from=date_from, date_to=date_to, **result
        )
    table = _subledger_table(
        report_key="customer_subledger",
        partner_name=partner.name,
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        date_from=date_from,
        date_to=date_to,
        result=result,
        lang=lang,
    )
    return build_export_response(format, f"customer-statement-{partner.name}", table)


@router.get("/subledger/vendor/{partner_id}", response_model=SubledgerResponse)
async def vendor_subledger(
    partner_id: UUID,
    date_from: date,
    date_to: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("payment.subledger.view")),
    service: SubledgerService = Depends(get_subledger_service),
    partner_repo: PartnerRepository = Depends(get_partner_repo),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    partner = await partner_repo.get_by_id(partner_id)
    if partner is None or partner.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendor not found")
    result = await service.vendor_subledger(
        company_id=ctx.company_id, partner_id=partner_id, date_from=date_from, date_to=date_to
    )
    if format == "json":
        return SubledgerResponse(
            partner_id=partner.id, partner_name=partner.name, date_from=date_from, date_to=date_to, **result
        )
    table = _subledger_table(
        report_key="vendor_subledger",
        partner_name=partner.name,
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        date_from=date_from,
        date_to=date_to,
        result=result,
        lang=lang,
    )
    return build_export_response(format, f"vendor-statement-{partner.name}", table)


@router.get("/aging/ar", response_model=AgingResponse)
async def ar_aging(
    as_of_date: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("payment.aging.view")),
    service: SubledgerService = Depends(get_subledger_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    rows = await service.ar_aging(company_id=ctx.company_id, as_of_date=as_of_date)
    if format == "json":
        return AgingResponse(as_of_date=as_of_date, rows=rows)
    table = _aging_table(
        report_key="ar_aging",
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        as_of_date=as_of_date,
        rows=rows,
        lang=lang,
    )
    return build_export_response(format, "ar-aging", table)


@router.get("/aging/ap", response_model=AgingResponse)
async def ap_aging(
    as_of_date: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("payment.aging.view")),
    service: SubledgerService = Depends(get_subledger_service),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    rows = await service.ap_aging(company_id=ctx.company_id, as_of_date=as_of_date)
    if format == "json":
        return AgingResponse(as_of_date=as_of_date, rows=rows)
    table = _aging_table(
        report_key="ap_aging",
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        as_of_date=as_of_date,
        rows=rows,
        lang=lang,
    )
    return build_export_response(format, "ap-aging", table)


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payload: PaymentCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("payment.create", require_branch=True)),
    service: PaymentService = Depends(get_payment_service),
):
    try:
        payment = await service.record_payment(
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            partner_id=payload.partner_id,
            payment_type=payload.payment_type,
            payment_date=payload.payment_date,
            amount=payload.amount,
            account_id=payload.account_id,
            reference=payload.reference,
            allocations=[a.model_dump() for a in payload.allocations],
            created_by=ctx.user_id,
        )
    except (OverAllocationError, InvalidAllocationTargetError, ValueError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return payment
