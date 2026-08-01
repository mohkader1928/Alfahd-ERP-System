"""Repository implementations for Accounting (Phase 8 §7 — Repository pattern)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.accounting.infrastructure.models import (
    Account,
    AccountType,
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
        result = await self.session.execute(select(FiscalPeriod).where(FiscalPeriod.id == period_id))
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
        within the date range."""
        stmt = (
            select(
                Account.id,
                Account.code,
                Account.name,
                func.coalesce(func.sum(JournalEntryLine.debit), 0).label("total_debit"),
                func.coalesce(func.sum(JournalEntryLine.credit), 0).label("total_credit"),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(
                JournalEntry.company_id == company_id,
                # "reversed" entries were genuinely posted to the ledger at
                # the time — only their *current* status changed to flag that
                # an offsetting reversal exists (FR-ACC-004: the original is
                # never edited or unposted). Excluding them here would break
                # the trial balance: original + reversal must net to zero,
                # not silently drop the original's half of the pair.
                JournalEntry.status.in_(["posted", "reversed"]),
                JournalEntry.entry_date >= date_from,
                JournalEntry.entry_date <= date_to,
            )
            .group_by(Account.id, Account.code, Account.name)
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
                "total_debit": Decimal(row.total_debit),
                "total_credit": Decimal(row.total_credit),
            }
            for row in result.all()
        ]

    async def account_balance(self, company_id: UUID, account_code: str, as_of_date: date) -> Decimal:
        """FR-RPT-003 — point-in-time balance for a single balance-sheet
        account (e.g. AR/AP), unlike `trial_balance` which is period-bound
        and meant for a full report. Returns debit-credit (positive for a
        normal-debit account like AR; caller flips sign for AP if a
        positive "amount owed" figure is wanted)."""
        result = await self.session.execute(
            select(
                func.coalesce(func.sum(JournalEntryLine.debit), 0),
                func.coalesce(func.sum(JournalEntryLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(Account, Account.id == JournalEntryLine.account_id)
            .where(
                JournalEntry.company_id == company_id,
                Account.code == account_code,
                JournalEntry.status.in_(["posted", "reversed"]),
                JournalEntry.entry_date <= as_of_date,
            )
        )
        total_debit, total_credit = result.one()
        # Same COALESCE-scale quirk noted in Sales/Purchasing's
        # sum_total_in_range — quantize explicitly for a consistent result
        # whether or not any rows matched.
        return (Decimal(total_debit) - Decimal(total_credit)).quantize(Decimal("0.0001"))
