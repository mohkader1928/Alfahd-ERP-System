"""Repository implementations for Accounting (Phase 8 §7 — Repository pattern)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.modules.accounting.infrastructure.models import (
    Account,
    AccountType,
    CostCenter,
    FiscalPeriod,
    Journal,
    JournalEntry,
    JournalEntryLine,
    TaxGroup,
    TaxRate,
)


class AccountTypeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str) -> AccountType | None:
        result = await self.session.execute(select(AccountType).where(AccountType.code == code))
        return result.scalar_one_or_none()


class AccountRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, account: Account) -> Account:
        self.session.add(account)
        await self.session.flush()
        return account

    async def update(self, account: Account) -> Account:
        await self.session.flush()
        return account

    async def get_by_id(self, account_id: UUID) -> Account | None:
        result = await self.session.execute(
            select(Account).where(Account.id == account_id, Account.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, company_id: UUID, code: str) -> Account | None:
        result = await self.session.execute(
            select(Account).where(
                Account.company_id == company_id, Account.code == code, Account.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID) -> list[Account]:
        result = await self.session.execute(
            select(Account)
            .where(Account.company_id == company_id, Account.deleted_at.is_(None))
            .order_by(Account.code)
        )
        return list(result.scalars().all())

    async def list_children(self, account_id: UUID) -> list[Account]:
        result = await self.session.execute(
            select(Account).where(Account.parent_id == account_id, Account.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def has_children(self, account_id: UUID) -> bool:
        result = await self.session.execute(
            select(Account.id).where(Account.parent_id == account_id, Account.deleted_at.is_(None)).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def has_transactions(self, account_id: UUID) -> bool:
        result = await self.session.execute(
            select(JournalEntryLine.id).where(JournalEntryLine.account_id == account_id).limit(1)
        )
        return result.scalar_one_or_none() is not None


class CostCenterRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, cost_center: CostCenter) -> CostCenter:
        self.session.add(cost_center)
        await self.session.flush()
        return cost_center

    async def update(self, cost_center: CostCenter) -> CostCenter:
        await self.session.flush()
        return cost_center

    async def get_by_id(self, company_id: UUID, cost_center_id: UUID) -> CostCenter | None:
        result = await self.session.execute(
            select(CostCenter).where(CostCenter.id == cost_center_id, CostCenter.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, company_id: UUID, name: str) -> CostCenter | None:
        result = await self.session.execute(
            select(CostCenter).where(
                CostCenter.company_id == company_id, func.lower(CostCenter.name) == name.lower()
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID) -> list[CostCenter]:
        result = await self.session.execute(
            select(CostCenter).where(CostCenter.company_id == company_id).order_by(CostCenter.name)
        )
        return list(result.scalars().all())

    async def has_transactions(self, cost_center_id: UUID) -> bool:
        result = await self.session.execute(
            select(JournalEntryLine.id).where(JournalEntryLine.cost_center_id == cost_center_id).limit(1)
        )
        return result.scalar_one_or_none() is not None


class JournalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, journal: Journal) -> Journal:
        self.session.add(journal)
        await self.session.flush()
        return journal

    async def get_by_code(self, company_id: UUID, code: str) -> Journal | None:
        result = await self.session.execute(
            select(Journal).where(Journal.company_id == company_id, Journal.code == code)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, journal_id: UUID) -> Journal | None:
        result = await self.session.execute(select(Journal).where(Journal.id == journal_id))
        return result.scalar_one_or_none()


class TaxRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_group(self, group: TaxGroup) -> TaxGroup:
        self.session.add(group)
        await self.session.flush()
        return group

    async def add_rate(self, rate: TaxRate) -> TaxRate:
        self.session.add(rate)
        await self.session.flush()
        return rate

    async def get_rate_by_id(self, rate_id: UUID) -> TaxRate | None:
        result = await self.session.execute(select(TaxRate).where(TaxRate.id == rate_id))
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID) -> list[TaxRate]:
        result = await self.session.execute(select(TaxRate).where(TaxRate.company_id == company_id))
        return list(result.scalars().all())


class FiscalPeriodRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, period: FiscalPeriod) -> FiscalPeriod:
        self.session.add(period)
        await self.session.flush()
        return period

    async def get_by_id(self, period_id: UUID) -> FiscalPeriod | None:
        result = await self.session.execute(
            select(FiscalPeriod).where(FiscalPeriod.id == period_id)
        )
        return result.scalar_one_or_none()

    async def find_covering(self, company_id: UUID, entry_date: date) -> FiscalPeriod | None:
        result = await self.session.execute(
            select(FiscalPeriod).where(
                FiscalPeriod.company_id == company_id,
                FiscalPeriod.period_start <= entry_date,
                FiscalPeriod.period_end >= entry_date,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID) -> list[FiscalPeriod]:
        result = await self.session.execute(
            select(FiscalPeriod)
            .where(FiscalPeriod.company_id == company_id)
            .order_by(FiscalPeriod.period_start.desc())
        )
        return list(result.scalars().all())


class JournalEntryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, entry: JournalEntry, lines: list[JournalEntryLine]) -> JournalEntry:
        self.session.add(entry)
        await self.session.flush()
        for line in lines:
            line.journal_entry_id = entry.id
            self.session.add(line)
        await self.session.flush()
        return entry

    async def get_by_id(self, entry_id: UUID) -> JournalEntry | None:
        result = await self.session.execute(select(JournalEntry).where(JournalEntry.id == entry_id))
        return result.scalar_one_or_none()

    async def get_lines(self, entry_id: UUID) -> list[JournalEntryLine]:
        result = await self.session.execute(
            select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == entry_id)
        )
        return list(result.scalars().all())

    async def list_by_company(self, company_id: UUID) -> list[JournalEntry]:
        result = await self.session.execute(
            select(JournalEntry)
            .where(JournalEntry.company_id == company_id)
            .order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
        )
        return list(result.scalars().all())

    async def trial_balance(
        self, company_id: UUID, date_from: date, date_to: date, branch_id: UUID | None = None
    ) -> list[dict]:
        """FR-ACC-009: aggregated debit/credit per account for posted entries
        within the date range, plus opening balance (all activity before
        date_from) so callers get: Opening | Period Debit | Period Credit |
        Closing Balance — the standard four-column trial balance layout."""

        # --- Opening balance sub-query (everything BEFORE the period) ----------
        # Computes net debit-minus-credit per account for all posted activity
        # strictly before date_from.  Aliased so the main join can reference it.
        JEL_open = aliased(JournalEntryLine)
        JE_open = aliased(JournalEntry)

        opening_sub = (
            select(
                JEL_open.account_id.label("account_id"),
                func.coalesce(func.sum(JEL_open.debit), 0).label("open_debit"),
                func.coalesce(func.sum(JEL_open.credit), 0).label("open_credit"),
            )
            .join(JE_open, JE_open.id == JEL_open.journal_entry_id)
            .where(
                JE_open.company_id == company_id,
                JE_open.status.in_(["posted", "reversed"]),
                JE_open.entry_date < date_from,
            )
            .group_by(JEL_open.account_id)
        )
        if branch_id is not None:
            opening_sub = opening_sub.where(JE_open.branch_id == branch_id)
        opening_sub = opening_sub.subquery("opening")

        # --- Period activity sub-query (within [date_from, date_to]) -----------
        JEL_period = aliased(JournalEntryLine)
        JE_period = aliased(JournalEntry)

        period_sub = (
            select(
                JEL_period.account_id.label("account_id"),
                func.coalesce(func.sum(JEL_period.debit), 0).label("period_debit"),
                func.coalesce(func.sum(JEL_period.credit), 0).label("period_credit"),
            )
            .join(JE_period, JE_period.id == JEL_period.journal_entry_id)
            .where(
                JE_period.company_id == company_id,
                # "reversed" entries were genuinely posted to the ledger at
                # the time — only their *current* status changed to flag that
                # an offsetting reversal exists (FR-ACC-004: the original is
                # never edited or unposted). Excluding them here would break
                # the trial balance: original + reversal must net to zero,
                # not silently drop the original's half of the pair.
                JE_period.status.in_(["posted", "reversed"]),
                JE_period.entry_date >= date_from,
                JE_period.entry_date <= date_to,
            )
            .group_by(JEL_period.account_id)
        )
        if branch_id is not None:
            period_sub = period_sub.where(JE_period.branch_id == branch_id)
        period_sub = period_sub.subquery("period")

        # --- Main query: accounts that have ANY activity (opening OR period) ---
        # We FULL OUTER JOIN the two sub-queries on account_id so that
        # accounts with only opening activity (no period moves) still appear
        # and vice-versa.  SQLAlchemy async doesn't support full outer join
        # directly on subqueries the same way; we union the two account_id
        # sets first so we always start from the authoritative Account table,
        # then left-join both sub-queries.
        stmt = (
            select(
                Account.id,
                Account.code,
                Account.name,
                Account.parent_id,
                Account.level,
                AccountType.code.label("type_code"),
                func.coalesce(opening_sub.c.open_debit, 0).label("open_debit"),
                func.coalesce(opening_sub.c.open_credit, 0).label("open_credit"),
                func.coalesce(period_sub.c.period_debit, 0).label("period_debit"),
                func.coalesce(period_sub.c.period_credit, 0).label("period_credit"),
            )
            .join(AccountType, AccountType.id == Account.account_type_id)
            .outerjoin(opening_sub, opening_sub.c.account_id == Account.id)
            .outerjoin(period_sub, period_sub.c.account_id == Account.id)
            .where(
                Account.company_id == company_id,
                # Only include accounts that actually have activity
                (
                    (opening_sub.c.account_id != None)  # noqa: E711
                    | (period_sub.c.account_id != None)  # noqa: E711
                ),
            )
            .order_by(Account.code)
        )

        result = await self.session.execute(stmt)
        rows = []
        for row in result.all():
            open_debit = Decimal(str(row.open_debit))
            open_credit = Decimal(str(row.open_credit))
            period_debit = Decimal(str(row.period_debit))
            period_credit = Decimal(str(row.period_credit))
            # Opening balance: signed debit-minus-credit (positive = net debit,
            # negative = net credit).  Callers apply the sign convention of the
            # account type themselves (debit-normal accounts present a positive
            # opening as a debit balance; credit-normal accounts invert it).
            opening_balance = open_debit - open_credit
            closing_balance = opening_balance + period_debit - period_credit
            rows.append(
                {
                    "account_id": row.id,
                    "account_code": row.code,
                    "account_name": row.name,
                    "parent_id": row.parent_id,
                    "level": row.level,
                    "account_type_code": row.type_code,
                    "opening_balance": opening_balance,
                    "period_debit": period_debit,
                    "period_credit": period_credit,
                    "closing_balance": closing_balance,
                    # Legacy aliases kept so any existing callers don't break
                    "total_debit": period_debit,
                    "total_credit": period_credit,
                }
            )
        return rows

    async def balances_by_type(
        self,
        company_id: UUID,
        date_from: date,
        date_to: date,
        account_type_codes: list[str],
        branch_id: UUID | None = None,
        cost_center_id: UUID | None = None,
    ) -> list[dict]:
        """Milestone 1 — Accounting Standardization: per-account debit/credit
        totals restricted to one or more account types (e.g. only
        'revenue'+'expense' for the Income Statement, or only
        'asset'+'liability'+'equity' for the Balance Sheet), including the
        account's own type code and parent id so the caller can group
        further (e.g. splitting Cost of Goods Sold out of Expenses by
        walking the parent chain) without a second round trip.

        `cost_center_id`, when given, restricts the totals to journal entry
        lines tagged with that cost center — used to answer "how much
        revenue/expense did this cost center generate" without a separate
        query shape."""
        stmt = (
            select(
                Account.id,
                Account.code,
                Account.name,
                Account.parent_id,
                Account.level,
                AccountType.code.label("type_code"),
                func.coalesce(func.sum(JournalEntryLine.debit), 0).label("total_debit"),
                func.coalesce(func.sum(JournalEntryLine.credit), 0).label("total_credit"),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(AccountType, AccountType.id == Account.account_type_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status.in_(["posted", "reversed"]),
                JournalEntry.entry_date >= date_from,
                JournalEntry.entry_date <= date_to,
                AccountType.code.in_(account_type_codes),
            )
            .group_by(Account.id, Account.code, Account.name, Account.parent_id, Account.level, AccountType.code)
            .order_by(Account.code)
        )
        if branch_id is not None:
            stmt = stmt.where(JournalEntry.branch_id == branch_id)
        if cost_center_id is not None:
            stmt = stmt.where(JournalEntryLine.cost_center_id == cost_center_id)

        result = await self.session.execute(stmt)
        return [
            {
                "account_id": row.id,
                "account_code": row.code,
                "account_name": row.name,
                "parent_id": row.parent_id,
                "level": row.level,
                "type_code": row.type_code,
                "total_debit": Decimal(row.total_debit),
                "total_credit": Decimal(row.total_credit),
            }
            for row in result.all()
        ]

    async def balances_by_cost_center(
        self,
        company_id: UUID,
        cost_center_id: UUID,
        date_from: date,
        date_to: date,
        branch_id: UUID | None = None,
    ) -> list[dict]:
        """Cost Center Report — every account with posted activity tagged to
        this cost center in the period, across all account types (a cost
        center can carry any kind of line, though revenue/expense is the
        primary use case), with its net debit/credit for the period. The
        caller filters out zero-balance accounts."""
        stmt = (
            select(
                Account.id,
                Account.code,
                Account.name,
                AccountType.code.label("type_code"),
                func.coalesce(func.sum(JournalEntryLine.debit), 0).label("total_debit"),
                func.coalesce(func.sum(JournalEntryLine.credit), 0).label("total_credit"),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(AccountType, AccountType.id == Account.account_type_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status.in_(["posted", "reversed"]),
                JournalEntry.entry_date >= date_from,
                JournalEntry.entry_date <= date_to,
                JournalEntryLine.cost_center_id == cost_center_id,
            )
            .group_by(Account.id, Account.code, Account.name, AccountType.code)
            .order_by(Account.code)
        )
        if branch_id is not None:
            stmt = stmt.where(JournalEntry.branch_id == branch_id)

        result = await self.session.execute(stmt)
        return [
            {
                "account_id": row.id,
                "account_code": row.code,
                "account_name": row.name,
                "type_code": row.type_code,
                "total_debit": Decimal(row.total_debit),
                "total_credit": Decimal(row.total_credit),
            }
            for row in result.all()
        ]

    async def general_ledger_lines(
        self,
        company_id: UUID,
        account_id: UUID,
        date_from: date,
        date_to: date,
        branch_id: UUID | None = None,
        cost_center_id: UUID | None = None,
    ) -> list[dict]:
        """Milestone 1 — one account's posted movements within a date range,
        oldest first, each carrying its journal entry id so the frontend can
        drill down to the source Journal Entry (and from there to whatever
        business document created it, via its `reference`). Each line also
        carries its own cost center (if any), and `cost_center_id` narrows
        the result to movements tagged with one specific cost center."""
        stmt = (
            select(
                JournalEntry.id.label("journal_entry_id"),
                JournalEntry.entry_date,
                JournalEntry.reference,
                JournalEntry.status,
                JournalEntry.source_table,
                JournalEntry.source_id,
                JournalEntryLine.debit,
                JournalEntryLine.credit,
                JournalEntryLine.description,
                JournalEntryLine.cost_center_id,
                CostCenter.name.label("cost_center_name"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .outerjoin(CostCenter, CostCenter.id == JournalEntryLine.cost_center_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntryLine.account_id == account_id,
                JournalEntry.status.in_(["posted", "reversed"]),
                JournalEntry.entry_date >= date_from,
                JournalEntry.entry_date <= date_to,
            )
            .order_by(JournalEntry.entry_date, JournalEntry.created_at)
        )
        if branch_id is not None:
            stmt = stmt.where(JournalEntry.branch_id == branch_id)
        if cost_center_id is not None:
            stmt = stmt.where(JournalEntryLine.cost_center_id == cost_center_id)

        result = await self.session.execute(stmt)
        return [
            {
                "journal_entry_id": row.journal_entry_id,
                "entry_date": row.entry_date,
                "reference": row.reference,
                "status": row.status,
                "debit": Decimal(row.debit),
                "credit": Decimal(row.credit),
                "description": row.description,
                "source_table": row.source_table,
                "source_id": row.source_id,
                "cost_center_id": row.cost_center_id,
                "cost_center_name": row.cost_center_name,
            }
            for row in result.all()
        ]

    async def account_balance_by_id(
        self,
        company_id: UUID,
        account_id: UUID,
        as_of_date: date,
        branch_id: UUID | None = None,
        cost_center_id: UUID | None = None,
    ) -> Decimal:
        """Same shape as `account_balance` (debit-credit, caller flips sign
        for a credit-normal account) but keyed by id rather than a hardcoded
        code — used for General Ledger's opening balance and the Balance
        Sheet, neither of which is limited to the two hardcoded AR/AP codes
        the original FR-RPT-003 method was written for. `cost_center_id`
        keeps the opening balance consistent with a cost-center-filtered
        General Ledger view."""
        stmt = (
            select(
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntryLine.account_id == account_id,
                JournalEntry.status.in_(["posted", "reversed"]),
                JournalEntry.entry_date < as_of_date,
            )
        )
        if branch_id is not None:
            stmt = stmt.where(JournalEntry.branch_id == branch_id)
        if cost_center_id is not None:
            stmt = stmt.where(JournalEntryLine.cost_center_id == cost_center_id)
        result = await self.session.execute(stmt)
        total_debit, total_credit = result.one()
        return (Decimal(total_debit) - Decimal(total_credit)).quantize(Decimal("0.0001"))

    async def account_balance_by_root_code(
        self, company_id: UUID, root_account_code: str, as_of_date: date
    ) -> Decimal:
        """Hardening fix — Dashboard cash/AR/AP KPIs were reading
        `account_balance(..., "1100"/"1200"/"2100", ...)`, an EXACT code
        match. The moment a company creates a second real account under
        one of these (e.g. a second bank account under "1100 Cash and
        Bank" via Chart of Accounts management), that parent is
        auto-promoted to a non-postable group account
        (ChartOfAccountsService.create_account) and every subsequent
        posting lands on the new child code instead — an exact-code
        lookup then silently stops seeing that activity, understating the
        dashboard KPI while the Trial Balance (which the same KPI links
        to) still shows the true total. This sums the account's ENTIRE
        subtree (itself + every descendant, however many levels of
        splitting occurred), the same shape ReportingService._cogs_account_ids
        already uses for the Income Statement's COGS bucket — reused here
        rather than reinvented. Company-scoped explicitly (not just via
        RLS) as this codebase's own belt-and-suspenders convention."""
        result = await self.session.execute(
            text("""
            WITH RECURSIVE subtree AS (
                SELECT id FROM account WHERE company_id = :company_id AND code = :root_code
                UNION ALL
                SELECT a.id FROM account a
                JOIN subtree s ON a.parent_id = s.id
                WHERE a.company_id = :company_id
            )
            SELECT
                COALESCE(SUM(jel.debit), 0) AS total_debit,
                COALESCE(SUM(jel.credit), 0) AS total_credit
            FROM journal_entry_line jel
            JOIN journal_entry je ON je.id = jel.journal_entry_id
            WHERE jel.account_id IN (SELECT id FROM subtree)
              AND je.company_id = :company_id
              AND je.status IN ('posted', 'reversed')
              AND je.entry_date <= :as_of_date
            """),
            {"company_id": company_id, "root_code": root_account_code, "as_of_date": as_of_date},
        )
        total_debit, total_credit = result.one()
        return (Decimal(total_debit) - Decimal(total_credit)).quantize(Decimal("0.0001"))
