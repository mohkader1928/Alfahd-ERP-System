"""Application services (use-case orchestration) for Accounting, Phase 8 §2."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from src.modules.accounting.domain.entities import (
    ACCOUNT_TYPES,
    PeriodClosedError,
    PostedEntryImmutableError,
)
from src.modules.accounting.domain.entities import (
    JournalEntry as DomainJournalEntry,
)
from src.modules.accounting.domain.entities import (
    JournalEntryLine as DomainJournalEntryLine,
)
from src.modules.accounting.infrastructure.models import (
    Account,
    FiscalPeriod,
    Journal,
    JournalEntry,
    JournalEntryLine,
    TaxGroup,
    TaxRate,
)
from src.modules.accounting.infrastructure.repositories import (
    AccountRepository,
    AccountTypeRepository,
    FiscalPeriodRepository,
    JournalEntryRepository,
    JournalRepository,
    TaxRepository,
)

# code, name, name_ar, type_code, parent_code
DEFAULT_SAUDI_COA: list[tuple[str, str, str, str, str | None]] = [
    ("1000", "Assets", "Assets AR", "asset", None),
    ("1100", "Cash and Bank", "Cash and Bank AR", "asset", "1000"),
    ("1200", "Accounts Receivable", "Accounts Receivable AR", "asset", "1000"),
    ("1300", "Inventory", "Inventory AR", "asset", "1000"),
    ("2000", "Liabilities", "Liabilities AR", "liability", None),
    ("2100", "Accounts Payable", "Accounts Payable AR", "liability", "2000"),
    ("2200", "VAT Payable", "VAT Payable AR", "liability", "2000"),
    ("2300", "Goods Received Not Invoiced", "GRNI AR", "liability", "2000"),
    ("3000", "Equity", "Equity AR", "equity", None),
    ("3100", "Owner's Capital", "Owner's Capital AR", "equity", "3000"),
    ("3200", "Retained Earnings", "Retained Earnings AR", "equity", "3000"),
    ("4000", "Revenue", "Revenue AR", "revenue", None),
    ("4100", "Sales Revenue", "Sales Revenue AR", "revenue", "4000"),
    ("5000", "Expenses", "Expenses AR", "expense", None),
    ("5100", "Cost of Goods Sold", "COGS AR", "expense", "5000"),
    ("5200", "Operating Expenses", "Operating Expenses AR", "expense", "5000"),
]


def _utcnow_naive() -> datetime:
    """`posted_at` (and every other timestamp column in the current schema)
    is `TIMESTAMP WITHOUT TIME ZONE` — always UTC by convention, but the
    driver rejects a tz-aware value against a naive column. Strip tzinfo
    here rather than switching the column type, which would be a
    schema-wide change beyond M1's scope.
    """
    return datetime.now(UTC).replace(tzinfo=None)


DEFAULT_JOURNALS = [
    ("SALES", "Sales Journal"),
    ("PURCH", "Purchases Journal"),
    ("BANK", "Bank Journal"),
    ("CASH", "Cash Journal"),
    ("GEN", "General Journal"),
]

# name, kind, rate_percent
DEFAULT_TAX_RATES = [
    ("Standard VAT 15%", "standard", Decimal("15.00")),
    ("Zero-Rated 0%", "zero_rated", Decimal("0.00")),
    ("Exempt", "exempt", Decimal("0.00")),
    ("Out of Scope", "out_of_scope", Decimal("0.00")),
]


class ChartOfAccountsService:
    """UC-ACC groundwork: seeds a company's CoA, journals, and tax rates.

    Called once during company onboarding — the Saudi default template from
    Phase 1 §5 (M1) rather than making every new company start from zero.
    """

    def __init__(
        self,
        account_repo: AccountRepository,
        account_type_repo: AccountTypeRepository,
        journal_repo: JournalRepository,
        tax_repo: TaxRepository,
    ):
        self.account_repo = account_repo
        self.account_type_repo = account_type_repo
        self.journal_repo = journal_repo
        self.tax_repo = tax_repo

    async def seed_default_chart_of_accounts(self, company_id: UUID) -> dict[str, Account]:
        accounts_by_code: dict[str, Account] = {}
        for code, name, name_ar, type_code, parent_code in DEFAULT_SAUDI_COA:
            account_type = await self.account_type_repo.get_by_code(type_code)
            if account_type is None:
                raise ValueError(f"Account type not seeded: {type_code}")
            parent = accounts_by_code.get(parent_code) if parent_code else None
            account = Account(
                id=uuid.uuid4(),
                company_id=company_id,
                code=code,
                name=name,
                name_ar=name_ar,
                account_type_id=account_type.id,
                parent_id=parent.id if parent else None,
            )
            await self.account_repo.add(account)
            accounts_by_code[code] = account
        return accounts_by_code

    async def seed_default_journals(
        self, company_id: UUID, accounts_by_code: dict[str, Account]
    ) -> None:
        journal_defaults = {
            "SALES": ("1200", "4100"),  # debit AR, credit Sales Revenue
            "PURCH": ("5100", "2100"),  # debit COGS, credit AP
            "BANK": ("1100", "1100"),
            "CASH": ("1100", "1100"),
            "GEN": (None, None),
        }
        for code, name in DEFAULT_JOURNALS:
            debit_code, credit_code = journal_defaults[code]
            journal = Journal(
                id=uuid.uuid4(),
                company_id=company_id,
                code=code,
                name=name,
                default_debit_account_id=accounts_by_code[debit_code].id if debit_code else None,
                default_credit_account_id=accounts_by_code[credit_code].id if credit_code else None,
            )
            await self.journal_repo.add(journal)

    async def seed_default_tax_rates(self, company_id: UUID) -> None:
        group = TaxGroup(id=uuid.uuid4(), company_id=company_id, name="Saudi VAT")
        await self.tax_repo.add_group(group)
        for name, kind, rate_percent in DEFAULT_TAX_RATES:
            rate = TaxRate(
                id=uuid.uuid4(),
                company_id=company_id,
                tax_group_id=group.id,
                name=name,
                kind=kind,
                rate_percent=rate_percent,
            )
            await self.tax_repo.add_rate(rate)

    async def create_account(
        self,
        *,
        company_id: UUID,
        code: str,
        name: str,
        name_ar: str | None,
        account_type_code: str,
        parent_id: UUID | None = None,
    ) -> Account:
        if account_type_code not in ACCOUNT_TYPES:
            raise ValueError(f"Unknown account type: {account_type_code}")
        existing = await self.account_repo.get_by_code(company_id, code)
        if existing is not None:
            raise ValueError(f"Account code already exists: {code}")
        account_type = await self.account_type_repo.get_by_code(account_type_code)
        account = Account(
            id=uuid.uuid4(),
            company_id=company_id,
            code=code,
            name=name,
            name_ar=name_ar,
            account_type_id=account_type.id,
            parent_id=parent_id,
        )
        return await self.account_repo.add(account)


class JournalEntryService:
    """UC-ACC-01 — create and post journal entries; enforces FR-ACC-002..004
    at the application layer (the DB trigger from Phase 7 §1.6 is the backstop).
    """

    def __init__(
        self,
        entry_repo: JournalEntryRepository,
        journal_repo: JournalRepository,
        account_repo: AccountRepository,
        period_repo: FiscalPeriodRepository,
    ):
        self.entry_repo = entry_repo
        self.journal_repo = journal_repo
        self.account_repo = account_repo
        self.period_repo = period_repo

    async def create_draft_entry(
        self,
        *,
        company_id: UUID,
        branch_id: UUID | None,
        journal_code: str,
        entry_date: date,
        reference: str | None,
        lines: list[dict],
        created_by: UUID,
        source_table: str | None = None,
        source_id: UUID | None = None,
    ) -> JournalEntry:
        journal = await self.journal_repo.get_by_code(company_id, journal_code)
        if journal is None:
            raise ValueError(f"Unknown journal code: {journal_code}")

        domain_lines = [
            DomainJournalEntryLine(
                account_id=line["account_id"],
                debit=Decimal(str(line.get("debit", 0))),
                credit=Decimal(str(line.get("credit", 0))),
                cost_center_id=line.get("cost_center_id"),
                description=line.get("description"),
            )
            for line in lines
        ]
        domain_entry = DomainJournalEntry(
            id=uuid.uuid4(), company_id=company_id, journal_id=journal.id, lines=domain_lines
        )
        domain_entry.assert_balanced()

        for line in domain_lines:
            account = await self.account_repo.get_by_id(line.account_id)
            if account is None or account.company_id != company_id:
                raise ValueError(f"Account not found in this company: {line.account_id}")

        orm_entry = JournalEntry(
            id=domain_entry.id,
            company_id=company_id,
            branch_id=branch_id,
            journal_id=journal.id,
            entry_date=entry_date,
            reference=reference,
            source_table=source_table,
            source_id=source_id,
            status="draft",
            created_by=created_by,
        )
        orm_lines = [
            JournalEntryLine(
                id=uuid.uuid4(),
                company_id=company_id,
                journal_entry_id=domain_entry.id,
                account_id=line.account_id,
                cost_center_id=line.cost_center_id,
                debit=line.debit,
                credit=line.credit,
                description=line.description,
            )
            for line in domain_lines
        ]
        return await self.entry_repo.add(orm_entry, orm_lines)

    async def post_entry(self, *, entry_id: UUID, company_id: UUID) -> JournalEntry:
        entry = await self.entry_repo.get_by_id(entry_id)
        if entry is None or entry.company_id != company_id:
            raise ValueError("Journal entry not found")
        if entry.status == "posted":
            raise PostedEntryImmutableError("This entry is already posted")

        period = await self.period_repo.find_covering(company_id, entry.entry_date)
        if period is not None and period.is_closed:
            raise PeriodClosedError(f"Fiscal period covering {entry.entry_date} is closed")

        lines = await self.entry_repo.get_lines(entry_id)
        domain_lines = [
            DomainJournalEntryLine(
                account_id=line_.account_id, debit=line_.debit, credit=line_.credit
            )
            for line_ in lines
        ]
        domain_entry = DomainJournalEntry(
            id=entry.id, company_id=company_id, journal_id=entry.journal_id, lines=domain_lines
        )
        domain_entry.assert_balanced()  # re-validated at post time, not just at draft creation

        entry.status = "posted"
        entry.posted_at = _utcnow_naive()
        entry.version += 1
        return entry

    async def reverse_entry(
        self, *, entry_id: UUID, company_id: UUID, created_by: UUID
    ) -> JournalEntry:
        original = await self.entry_repo.get_by_id(entry_id)
        if original is None or original.company_id != company_id:
            raise ValueError("Journal entry not found")
        if original.status != "posted":
            raise ValueError("Only a posted entry can be reversed")

        original_lines = await self.entry_repo.get_lines(entry_id)

        reversal = JournalEntry(
            id=uuid.uuid4(),
            company_id=company_id,
            branch_id=original.branch_id,
            journal_id=original.journal_id,
            entry_date=date.today(),
            reference=f"Reversal of {original.id}",
            status="posted",
            posted_at=_utcnow_naive(),
            created_by=created_by,
        )
        reversal_lines = [
            JournalEntryLine(
                id=uuid.uuid4(),
                company_id=company_id,
                journal_entry_id=reversal.id,
                account_id=line_.account_id,
                cost_center_id=line_.cost_center_id,
                debit=line_.credit,  # swapped — this is what makes it a reversal
                credit=line_.debit,
                description=f"Reversal: {line_.description or ''}".strip(),
            )
            for line_ in original_lines
        ]
        await self.entry_repo.add(reversal, reversal_lines)

        original.status = "reversed"
        original.reversed_entry_id = reversal.id
        original.version += 1

        return reversal


class ReportingService:
    """FR-ACC-009 — Trial Balance, plus Milestone 1 (Accounting
    Standardization): General Ledger, Income Statement, Balance Sheet. Every
    figure below is derived from real posted Journal Entries — nothing here
    is a separate reporting table or precomputed snapshot, so a report is
    always traceable back to Journal Entry -> Journal Entry Lines -> the
    Account it hit, per the Owner's "Evidence > Claims" / traceability rule."""

    # Cost of Goods Sold's own root account code in the seeded Chart of
    # Accounts (`5000 Expenses` -> `5100 Cost of Goods Sold` -> ...). Any
    # expense account that is 5100 itself, or nests under it, is COGS;
    # every other expense account is an Operating Expense. This mirrors the
    # grouping the Chart of Accounts was already seeded with in Phase 11 —
    # it is not a new convention invented for this report.
    _COGS_ROOT_CODE = "5100"

    def __init__(
        self, entry_repo: JournalEntryRepository, account_repo: AccountRepository | None = None
    ):
        self.entry_repo = entry_repo
        self.account_repo = account_repo

    async def trial_balance(
        self, *, company_id: UUID, date_from: date, date_to: date, branch_id: UUID | None = None
    ) -> list[dict]:
        return await self.entry_repo.trial_balance(company_id, date_from, date_to, branch_id)

    async def general_ledger(
        self,
        *,
        company_id: UUID,
        account_id: UUID,
        date_from: date,
        date_to: date,
        branch_id: UUID | None = None,
    ) -> dict:
        """Milestone 1 — one account's ledger: opening balance (everything
        posted before `date_from`), every movement in range with a running
        balance, and a closing balance — with each line traceable to the
        Journal Entry that produced it (FR: drill-down to source)."""
        opening = await self.entry_repo.account_balance_by_id(
            company_id, account_id, date_from, branch_id
        )
        lines = await self.entry_repo.general_ledger_lines(
            company_id, account_id, date_from, date_to, branch_id
        )

        running = opening
        out_lines = []
        for line in lines:
            running = running + line["debit"] - line["credit"]
            out_lines.append({**line, "running_balance": running})

        return {"opening_balance": opening, "lines": out_lines, "closing_balance": running}

    async def income_statement(
        self, *, company_id: UUID, date_from: date, date_to: date, branch_id: UUID | None = None
    ) -> dict:
        """Milestone 1 — Revenue / COGS / Gross Profit / Operating Expenses
        / Net Income for the period, built entirely from posted Journal
        Entry activity within [date_from, date_to] — a period report, not a
        cumulative one, matching standard P&L semantics."""
        rows = await self.entry_repo.balances_by_type(
            company_id, date_from, date_to, ["revenue", "expense"], branch_id
        )
        cogs_subtree = await self._cogs_account_ids(company_id) if self.account_repo else set()

        revenue_accounts, cogs_accounts, opex_accounts = [], [], []
        revenue_total = cogs_total = opex_total = Decimal("0.0000")
        for row in rows:
            if row["type_code"] == "revenue":
                # Revenue is credit-normal: a positive figure means more was
                # earned than debited back out (e.g. via a credit note).
                amount = row["total_credit"] - row["total_debit"]
                revenue_accounts.append({**row, "amount": amount})
                revenue_total += amount
            else:  # expense — debit-normal
                amount = row["total_debit"] - row["total_credit"]
                bucket = cogs_accounts if row["account_id"] in cogs_subtree else opex_accounts
                bucket.append({**row, "amount": amount})
                if row["account_id"] in cogs_subtree:
                    cogs_total += amount
                else:
                    opex_total += amount

        gross_profit = revenue_total - cogs_total
        operating_income = gross_profit - opex_total
        return {
            "revenue_accounts": revenue_accounts,
            "revenue_total": revenue_total,
            "cogs_accounts": cogs_accounts,
            "cogs_total": cogs_total,
            "gross_profit": gross_profit,
            "opex_accounts": opex_accounts,
            "opex_total": opex_total,
            "operating_income": operating_income,
            # No accounts exist yet for a distinct "other income/expense"
            # bucket in the current Chart of Accounts — reported as 0 rather
            # than invented, so Net Income is Operating Income for now. If a
            # company adds such accounts later, this is the one place that
            # would need a real "other" classification rule, not a silent gap.
            "net_income": operating_income,
        }

    async def balance_sheet(
        self, *, company_id: UUID, as_of_date: date, branch_id: UUID | None = None
    ) -> dict:
        """Milestone 1 — Assets / Liabilities / Equity as of a date. There is
        no period-close step yet that moves prior periods' net income into
        Retained Earnings (FiscalPeriodService.close_period only locks the
        period against new postings — see docs), so this computes net
        income since inception as an explicit "Current Earnings (unclosed)"
        equity line. That keeps the fundamental identity Assets = Liabilities
        + Equity true using only real, derived Journal Entry data — no
        closing entries are posted, nothing is mutated, nothing is faked."""
        from datetime import date as _date

        inception = _date(1900, 1, 1)
        rows = await self.entry_repo.balances_by_type(
            company_id, inception, as_of_date, ["asset", "liability", "equity"], branch_id
        )
        assets, liabilities, equity = [], [], []
        assets_total = liabilities_total = equity_total = Decimal("0.0000")
        for row in rows:
            if row["type_code"] == "asset":
                amount = row["total_debit"] - row["total_credit"]
                assets.append({**row, "amount": amount})
                assets_total += amount
            elif row["type_code"] == "liability":
                amount = row["total_credit"] - row["total_debit"]
                liabilities.append({**row, "amount": amount})
                liabilities_total += amount
            else:
                amount = row["total_credit"] - row["total_debit"]
                equity.append({**row, "amount": amount})
                equity_total += amount

        income = await self.income_statement(
            company_id=company_id, date_from=inception, date_to=as_of_date, branch_id=branch_id
        )
        current_earnings = income["net_income"]
        equity_total += current_earnings

        return {
            "assets": assets,
            "assets_total": assets_total,
            "liabilities": liabilities,
            "liabilities_total": liabilities_total,
            "equity": equity,
            "equity_total": equity_total,
            "current_earnings": current_earnings,
            "total_liabilities_and_equity": liabilities_total + equity_total,
        }

    async def _cogs_account_ids(self, company_id: UUID) -> set[UUID]:
        accounts = await self.account_repo.list_by_company(company_id)
        cogs_root = next((a for a in accounts if a.code == self._COGS_ROOT_CODE), None)
        if cogs_root is None:
            return set()

        result: set[UUID] = {cogs_root.id}
        changed = True
        while changed:
            changed = False
            for a in accounts:
                if a.parent_id in result and a.id not in result:
                    result.add(a.id)
                    changed = True
        return result


class FiscalPeriodService:
    """FR-ACC-011 — Period Closing."""

    def __init__(self, period_repo: FiscalPeriodRepository):
        self.period_repo = period_repo

    async def create_period(
        self, *, company_id: UUID, period_start: date, period_end: date
    ) -> FiscalPeriod:
        period = FiscalPeriod(
            id=uuid.uuid4(), company_id=company_id, period_start=period_start, period_end=period_end
        )
        return await self.period_repo.add(period)

    async def close_period(self, *, period_id: UUID, company_id: UUID) -> FiscalPeriod:
        period = await self.period_repo.get_by_id(period_id)
        if period is None or period.company_id != company_id:
            raise ValueError("Fiscal period not found")
        period.is_closed = True
        return period
