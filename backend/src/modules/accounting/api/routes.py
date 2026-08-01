"""FastAPI routes for Accounting, per Phase 10 §6.2."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.api.deps import (
    get_account_repo,
    get_account_type_repo,
    get_fiscal_period_repo,
    get_journal_entry_repo,
    get_journal_repo,
    require_permission,
)
from src.modules.accounting.api.schemas import (
    AccountCreateRequest,
    AccountOut,
    FiscalPeriodCreateRequest,
    FiscalPeriodOut,
    JournalEntryCreateRequest,
    JournalEntryDetailResponse,
    JournalEntryOut,
    TrialBalanceRow,
)
from src.modules.accounting.application.services import (
    ChartOfAccountsService,
    FiscalPeriodService,
    JournalEntryService,
    ReportingService,
)
from src.modules.accounting.domain.entities import (
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
)
from src.modules.identity.infrastructure.repositories import AuditLogRepository
from src.shared.domain.base_entity import DomainError
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext

router = APIRouter()


@router.get("/chart-of-accounts", response_model=list[AccountOut])
async def list_chart_of_accounts(
    ctx: AuthContext = Depends(require_permission("accounting.chart_of_accounts.view")),
    account_repo: AccountRepository = Depends(get_account_repo),
):
    return await account_repo.list_by_company(ctx.company_id)


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

    service = ChartOfAccountsService(account_repo, account_type_repo, journal_repo, TaxRepository(db))
    try:
        account = await service.create_account(
            company_id=ctx.company_id,
            code=payload.code,
            name=payload.name,
            name_ar=payload.name_ar,
            account_type_code=payload.account_type_code,
            parent_id=payload.parent_id,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    await db.commit()
    return account


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


@router.post("/journal-entries", response_model=JournalEntryOut, status_code=status.HTTP_201_CREATED)
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
    ctx: AuthContext = Depends(require_permission("accounting.reports.trial_balance.view")),
    entry_repo: JournalEntryRepository = Depends(get_journal_entry_repo),
):
    service = ReportingService(entry_repo)
    return await service.trial_balance(
        company_id=ctx.company_id, date_from=date_from, date_to=date_to, branch_id=ctx.branch_id
    )


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
        period = await service.close_period(period_id=_uuid.UUID(period_id), company_id=ctx.company_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    await db.commit()
    return period
