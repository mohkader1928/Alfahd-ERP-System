"""FastAPI routes for Accounting, per Phase 10 §6.2."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.api.deps import (
    get_account_repo,
    get_account_type_repo,
    get_fiscal_period_repo,
    get_journal_entry_repo,
    get_journal_repo,
    get_tax_repo,
    require_permission,
)
from src.modules.accounting.api.schemas import (
    AccountCreateRequest,
    AccountOut,
    AccountUpdateRequest,
    BalanceSheetResponse,
    FiscalPeriodCreateRequest,
    FiscalPeriodOut,
    GeneralLedgerResponse,
    IncomeStatementResponse,
    JournalEntryCreateRequest,
    JournalEntryDetailResponse,
    JournalEntryOut,
    TaxRateOut,
    TrialBalanceRow,
)
from src.modules.accounting.application.services import (
    _UNSET,
    ChartOfAccountsService,
    FiscalPeriodService,
    JournalEntryService,
    ReportingService,
)
from src.modules.accounting.domain.entities import (
    EntryNotDraftError,
    PeriodClosedError,
    PostedEntryImmutableError,
    UnbalancedEntryError,
)
from src.modules.accounting.infrastructure.repositories import (
    AccountRepository,
    AccountTypeRepository,
    FiscalPeriodRepository,
    JournalEntryRepository,
    JournalRepository,
    TaxRepository,
)
from src.modules.identity.api.deps import get_company_repo
from src.modules.identity.infrastructure.repositories import AuditLogRepository, CompanyRepository
from src.shared.domain.base_entity import DomainError
from src.shared.infrastructure.db.session import get_db
from src.shared.reporting.company_name import resolve_company_name
from src.shared.reporting.export_render import ReportColumn, ReportTable
from src.shared.reporting.export_response import build_export_response
from src.shared.reporting.formatting import format_amount, format_date_str
from src.shared.reporting.labels import label, title
from src.shared.security.auth_context import AuthContext

router = APIRouter()

ExportFormatParam = Literal["json", "pdf", "xlsx"]


@router.get("/chart-of-accounts", response_model=list[AccountOut])
async def list_chart_of_accounts(
    ctx: AuthContext = Depends(require_permission("accounting.chart_of_accounts.view")),
    account_repo: AccountRepository = Depends(get_account_repo),
):
    return await account_repo.list_by_company(ctx.company_id)


@router.get("/tax-rates", response_model=list[TaxRateOut])
async def list_tax_rates(
    ctx: AuthContext = Depends(require_permission("accounting.tax_rate.view")),
    tax_repo: TaxRepository = Depends(get_tax_repo),
):
    """P0-1 (Phase-One VAT hardening): the company's real, seeded TaxRate
    configuration (`ChartOfAccountsService.seed_default_tax_rates`) — the
    exact mechanism a picker must bind to instead of a hardcoded rate.
    Read-only for now; TaxRate CRUD is a separate, later concern."""
    return await tax_repo.list_by_company(ctx.company_id)


@router.post("/chart-of-accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("accounting.chart_of_accounts.manage")),
    account_repo: AccountRepository = Depends(get_account_repo),
    account_type_repo: AccountTypeRepository = Depends(get_account_type_repo),
    journal_repo: JournalRepository = Depends(get_journal_repo),
):
    from src.modules.accounting.infrastructure.repositories import TaxRepository

    service = ChartOfAccountsService(
        account_repo, account_type_repo, journal_repo, TaxRepository(db)
    )
    try:
        account = await service.create_account(
            company_id=ctx.company_id,
            code=payload.code,
            name=payload.name,
            name_ar=payload.name_ar,
            account_type_code=payload.account_type_code,
            parent_id=payload.parent_id,
            is_group=payload.is_group,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return account


@router.patch("/chart-of-accounts/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: UUID,
    payload: AccountUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("accounting.chart_of_accounts.manage")),
    account_repo: AccountRepository = Depends(get_account_repo),
    account_type_repo: AccountTypeRepository = Depends(get_account_type_repo),
    journal_repo: JournalRepository = Depends(get_journal_repo),
):
    from src.modules.accounting.infrastructure.repositories import TaxRepository

    before = await account_repo.get_by_id(account_id)
    if before is None or before.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    before_parent_id, before_is_group, before_is_active = before.parent_id, before.is_group, before.is_active

    service = ChartOfAccountsService(account_repo, account_type_repo, journal_repo, TaxRepository(db))
    try:
        account = await service.update_account(
            account_id=account_id,
            company_id=ctx.company_id,
            code=payload.code,
            name=payload.name,
            name_ar=payload.name_ar,
            account_type_code=payload.account_type_code,
            parent_id=payload.parent_id if payload.parent_id_set else _UNSET,
            is_group=payload.is_group,
            is_active=payload.is_active,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    # P0-4: hierarchy changes and posting-eligibility flips are the two
    # audit-worthy edits here -- code/name/type churn is cosmetic by
    # comparison and isn't logged, same selectivity the short-close/reopen
    # audit entries elsewhere in the codebase already use.
    if payload.parent_id_set and account.parent_id != before_parent_id:
        await AuditLogRepository(db).record(
            tenant_id=ctx.tenant_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            target_table="account",
            target_id=account_id,
            field_name="parent_id",
            old_value=str(before_parent_id) if before_parent_id else None,
            new_value=str(account.parent_id) if account.parent_id else None,
        )
    if account.is_group != before_is_group:
        await AuditLogRepository(db).record(
            tenant_id=ctx.tenant_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            target_table="account",
            target_id=account_id,
            field_name="is_group",
            old_value=str(before_is_group),
            new_value=str(account.is_group),
        )
    if account.is_active != before_is_active:
        await AuditLogRepository(db).record(
            tenant_id=ctx.tenant_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            target_table="account",
            target_id=account_id,
            field_name="is_active",
            old_value=str(before_is_active),
            new_value=str(account.is_active),
        )

    await db.commit()
    return account


@router.delete("/chart-of-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("accounting.chart_of_accounts.manage")),
    account_repo: AccountRepository = Depends(get_account_repo),
    account_type_repo: AccountTypeRepository = Depends(get_account_type_repo),
    journal_repo: JournalRepository = Depends(get_journal_repo),
):
    from src.modules.accounting.infrastructure.repositories import TaxRepository

    service = ChartOfAccountsService(account_repo, account_type_repo, journal_repo, TaxRepository(db))
    try:
        await service.delete_account(account_id=account_id, company_id=ctx.company_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await AuditLogRepository(db).record(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        target_table="account",
        target_id=account_id,
        field_name="deleted_at",
        old_value=None,
        new_value="deleted",
    )
    await db.commit()


@router.get("/journal-entries", response_model=list[JournalEntryOut])
async def list_journal_entries(
    ctx: AuthContext = Depends(require_permission("accounting.journal_entry.view")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
):
    return await entry_repo.list_by_company(ctx.company_id)


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryDetailResponse)
async def get_journal_entry(
    entry_id: str,
    ctx: AuthContext = Depends(require_permission("accounting.journal_entry.view")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
):
    import uuid as _uuid

    entry = await entry_repo.get_by_id(_uuid.UUID(entry_id))
    if entry is None or entry.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Journal entry not found")
    lines = await entry_repo.get_lines(entry.id)
    return JournalEntryDetailResponse(entry=entry, lines=lines)


@router.post(
    "/journal-entries", response_model=JournalEntryOut, status_code=status.HTTP_201_CREATED
)
async def create_journal_entry(
    payload: JournalEntryCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("accounting.journal_entry.create")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
    journal_repo: JournalRepository = Depends(get_journal_repo),
    account_repo: AccountRepository = Depends(get_account_repo),
    period_repo: FiscalPeriodRepository = Depends(get_fiscal_period_repo),
):
    service = JournalEntryService(entry_repo, journal_repo, account_repo, period_repo)
    try:
        entry = await service.create_draft_entry(
            company_id=ctx.company_id,
            branch_id=ctx.branch_id,
            journal_code=payload.journal_code,
            entry_date=payload.entry_date,
            reference=payload.reference,
            description=payload.description,
            lines=[line.model_dump() for line in payload.lines],
            created_by=ctx.user_id,
        )
    except (ValueError, DomainError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return entry


@router.post("/journal-entries/{entry_id}:post", response_model=JournalEntryOut)
async def post_journal_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("accounting.journal_entry.post")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
    journal_repo: JournalRepository = Depends(get_journal_repo),
    account_repo: AccountRepository = Depends(get_account_repo),
    period_repo: FiscalPeriodRepository = Depends(get_fiscal_period_repo),
):
    import uuid as _uuid

    service = JournalEntryService(entry_repo, journal_repo, account_repo, period_repo)
    try:
        entry = await service.post_entry(entry_id=_uuid.UUID(entry_id), company_id=ctx.company_id)
    except (UnbalancedEntryError, PostedEntryImmutableError, PeriodClosedError) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    # FR-CORE-022: financial state transitions are exactly the kind of
    # "sensitive field" change the audit trail exists for.
    await AuditLogRepository(db).record(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        target_table="journal_entry",
        target_id=entry.id,
        field_name="status",
        old_value="draft",
        new_value="posted",
    )

    await db.commit()
    return entry


@router.post("/journal-entries/{entry_id}:cancel", response_model=JournalEntryOut)
async def cancel_journal_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("accounting.journal_entry.cancel")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
    journal_repo: JournalRepository = Depends(get_journal_repo),
    account_repo: AccountRepository = Depends(get_account_repo),
    period_repo: FiscalPeriodRepository = Depends(get_fiscal_period_repo),
):
    import uuid as _uuid

    service = JournalEntryService(entry_repo, journal_repo, account_repo, period_repo)
    try:
        entry = await service.cancel_draft_entry(entry_id=_uuid.UUID(entry_id), company_id=ctx.company_id)
    except EntryNotDraftError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    await AuditLogRepository(db).record(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        target_table="journal_entry",
        target_id=entry.id,
        field_name="status",
        old_value="draft",
        new_value="cancelled",
    )

    await db.commit()
    return entry


@router.post("/journal-entries/{entry_id}:reverse", response_model=JournalEntryOut)
async def reverse_journal_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("accounting.journal_entry.reverse")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
    journal_repo: JournalRepository = Depends(get_journal_repo),
    account_repo: AccountRepository = Depends(get_account_repo),
    period_repo: FiscalPeriodRepository = Depends(get_fiscal_period_repo),
):
    import uuid as _uuid

    service = JournalEntryService(entry_repo, journal_repo, account_repo, period_repo)
    try:
        reversal = await service.reverse_entry(
            entry_id=_uuid.UUID(entry_id), company_id=ctx.company_id, created_by=ctx.user_id
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await AuditLogRepository(db).record(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        target_table="journal_entry",
        target_id=_uuid.UUID(entry_id),
        field_name="status",
        old_value="posted",
        new_value="reversed",
    )

    await db.commit()
    return reversal


@router.get("/reports/trial-balance", response_model=list[TrialBalanceRow])
async def trial_balance(
    date_from: date,
    date_to: date,
    detail_level: int | None = None,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("accounting.reports.trial_balance.view")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
    account_repo: AccountRepository = Depends(get_account_repo),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    service = ReportingService(entry_repo, account_repo)
    rows = await service.trial_balance(
        company_id=ctx.company_id,
        date_from=date_from,
        date_to=date_to,
        branch_id=ctx.branch_id,
        detail_level=detail_level,
    )
    if format == "json":
        return rows

    debit_normal = {"asset", "expense"}
    table_rows: list[list[str]] = []
    highlight: set[int] = set()
    total_debit = total_credit = 0
    for i, r in enumerate(rows):
        closing = r["closing_balance"]
        opening = r["opening_balance"]
        is_debit_normal = r["account_type_code"] in debit_normal
        if (is_debit_normal and closing < 0) or (not is_debit_normal and closing > 0):
            highlight.add(i)
        dr_close = closing if closing > 0 else 0
        cr_close = -closing if closing < 0 else 0
        table_rows.append(
            [
                f"{r['account_code']} — {r['account_name']}",
                format_amount(opening if opening > 0 else 0),
                format_amount(-opening if opening < 0 else 0),
                format_amount(r["period_debit"]),
                format_amount(r["period_credit"]),
                format_amount(dr_close),
                format_amount(cr_close),
            ]
        )
        total_debit += r["period_debit"]
        total_credit += r["period_credit"]
    table = ReportTable(
        title=title(lang, "trial_balance"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f"{date_from} — {date_to}",
        columns=[
            ReportColumn(label(lang, "account")),
            ReportColumn(f'{label(lang, "opening_balance")} ({label(lang, "debit")})', "end"),
            ReportColumn(f'{label(lang, "opening_balance")} ({label(lang, "credit")})', "end"),
            ReportColumn(label(lang, "debit"), "end"),
            ReportColumn(label(lang, "credit"), "end"),
            ReportColumn(f'{label(lang, "closing_balance")} ({label(lang, "debit")})', "end"),
            ReportColumn(f'{label(lang, "closing_balance")} ({label(lang, "credit")})', "end"),
        ],
        rows=table_rows,
        totals=[
            label(lang, "total"),
            "",
            "",
            format_amount(total_debit),
            format_amount(total_credit),
            "",
            "",
        ],
        highlight_rows=highlight,
        rtl=lang == "ar",
    )
    return build_export_response(format, "trial-balance", table)


@router.get("/reports/general-ledger", response_model=GeneralLedgerResponse)
async def general_ledger(
    account_id: str,
    date_from: date,
    date_to: date,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("accounting.reports.general_ledger.view")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
    account_repo: AccountRepository = Depends(get_account_repo),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    import uuid as _uuid

    account = await account_repo.get_by_id(_uuid.UUID(account_id))
    if account is None or account.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")

    service = ReportingService(entry_repo)
    result = await service.general_ledger(
        company_id=ctx.company_id,
        account_id=account.id,
        date_from=date_from,
        date_to=date_to,
        branch_id=ctx.branch_id,
    )
    if format == "json":
        return GeneralLedgerResponse(
            account_id=account.id, account_code=account.code, account_name=account.name, **result
        )

    table_rows = [
        [
            format_date_str(line["entry_date"]),
            line["reference"] or "",
            line["description"] or "",
            format_amount(line["debit"]),
            format_amount(line["credit"]),
            format_amount(line["running_balance"]),
        ]
        for line in result["lines"]
    ]
    table = ReportTable(
        title=f'{title(lang, "general_ledger")} — {account.code} {account.name}',
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f"{date_from} — {date_to}",
        columns=[
            ReportColumn(label(lang, "date")),
            ReportColumn(label(lang, "reference")),
            ReportColumn(label(lang, "description")),
            ReportColumn(label(lang, "debit"), "end"),
            ReportColumn(label(lang, "credit"), "end"),
            ReportColumn(label(lang, "running_balance"), "end"),
        ],
        rows=[
            [
                "",
                "",
                label(lang, "opening_balance"),
                "",
                "",
                format_amount(result["opening_balance"]),
            ],
            *table_rows,
        ],
        totals=["", "", label(lang, "closing_balance"), "", "", format_amount(result["closing_balance"])],
        rtl=lang == "ar",
    )
    return build_export_response(format, f"general-ledger-{account.code}", table)


@router.get("/reports/income-statement", response_model=IncomeStatementResponse)
async def income_statement(
    date_from: date,
    date_to: date,
    detail_level: int | None = None,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("accounting.reports.income_statement.view")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
    account_repo: AccountRepository = Depends(get_account_repo),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    service = ReportingService(entry_repo, account_repo)
    result = await service.income_statement(
        company_id=ctx.company_id,
        date_from=date_from,
        date_to=date_to,
        branch_id=ctx.branch_id,
        detail_level=detail_level,
    )
    if format == "json":
        return IncomeStatementResponse(date_from=date_from, date_to=date_to, **result)

    def section(section_label: str, rows: list, section_total) -> list[list[str]]:
        out = [[section_label, ""]]
        out += [
            [f"{r['account_code']} — {r['account_name']}", format_amount(r["amount"])] for r in rows
        ]
        out.append([f'{label(lang, "total")} — {section_label}', format_amount(section_total)])
        return out

    table_rows = (
        section(label(lang, "revenue"), result["revenue_accounts"], result["revenue_total"])
        + section("COGS", result["cogs_accounts"], result["cogs_total"])
        + [["Gross Profit", format_amount(result["gross_profit"])]]
        + section("OpEx", result["opex_accounts"], result["opex_total"])
        + [["Operating Income", format_amount(result["operating_income"])]]
    )
    table = ReportTable(
        title=title(lang, "income_statement"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f"{date_from} — {date_to}",
        columns=[ReportColumn(label(lang, "account")), ReportColumn(label(lang, "amount"), "end")],
        rows=table_rows,
        totals=["Net Income", format_amount(result["net_income"])],
        rtl=lang == "ar",
    )
    return build_export_response(format, "income-statement", table)


@router.get("/reports/balance-sheet", response_model=BalanceSheetResponse)
async def balance_sheet(
    as_of_date: date,
    detail_level: int | None = None,
    format: ExportFormatParam = "json",
    lang: Literal["ar", "en"] = "ar",
    ctx: AuthContext = Depends(require_permission("accounting.reports.balance_sheet.view")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
    account_repo: AccountRepository = Depends(get_account_repo),
    company_repo: CompanyRepository = Depends(get_company_repo),
):
    service = ReportingService(entry_repo, account_repo)
    result = await service.balance_sheet(
        company_id=ctx.company_id,
        as_of_date=as_of_date,
        branch_id=ctx.branch_id,
        detail_level=detail_level,
    )
    if format == "json":
        return BalanceSheetResponse(as_of_date=as_of_date, **result)

    def section(section_label: str, rows: list, section_total) -> list[list[str]]:
        out = [[section_label, ""]]
        out += [
            [f"{r['account_code']} — {r['account_name']}", format_amount(r["amount"])] for r in rows
        ]
        out.append([f'{label(lang, "total")} — {section_label}', format_amount(section_total)])
        return out

    table_rows = (
        section("Assets", result["assets"], result["assets_total"])
        + section("Liabilities", result["liabilities"], result["liabilities_total"])
        + section("Equity", result["equity"], result["equity_total"])
        + [["Current Earnings", format_amount(result["current_earnings"])]]
    )
    table = ReportTable(
        title=title(lang, "balance_sheet"),
        company_name=await resolve_company_name(company_repo, ctx.company_id, lang),
        subtitle=f'{label(lang, "date")}: {as_of_date}',
        columns=[ReportColumn(label(lang, "account")), ReportColumn(label(lang, "amount"), "end")],
        rows=table_rows,
        totals=["Total Liabilities & Equity", format_amount(result["total_liabilities_and_equity"])],
        rtl=lang == "ar",
    )
    return build_export_response(format, "balance-sheet", table)


@router.get("/fiscal-periods", response_model=list[FiscalPeriodOut])
async def list_fiscal_periods(
    ctx: AuthContext = Depends(require_permission("accounting.fiscal_period.manage")),
    period_repo: FiscalPeriodRepository = Depends(get_fiscal_period_repo),
):
    """P0-2 (Phase-One period-closing GUI): exposes the existing
    FiscalPeriod mechanism (FR-ACC-011) for a real list screen — until now
    only `create` and `:close` existed with no way to see what periods a
    company has. Reuses the existing `accounting.fiscal_period.manage`
    permission rather than introducing a separate view-only tier."""
    return await period_repo.list_by_company(ctx.company_id)


@router.post("/fiscal-periods", response_model=FiscalPeriodOut, status_code=status.HTTP_201_CREATED)
async def create_fiscal_period(
    payload: FiscalPeriodCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("accounting.fiscal_period.manage")),
    period_repo: FiscalPeriodRepository = Depends(get_fiscal_period_repo),
):
    service = FiscalPeriodService(period_repo)
    period = await service.create_period(
        company_id=ctx.company_id, period_start=payload.period_start, period_end=payload.period_end
    )
    await db.commit()
    return period


@router.post("/fiscal-periods/{period_id}:close", response_model=FiscalPeriodOut)
async def close_fiscal_period(
    period_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("accounting.fiscal_period.manage")),
    period_repo: FiscalPeriodRepository = Depends(get_fiscal_period_repo),
):
    import uuid as _uuid

    service = FiscalPeriodService(period_repo)
    try:
        period = await service.close_period(
            period_id=_uuid.UUID(period_id), company_id=ctx.company_id
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    await db.commit()
    return period
