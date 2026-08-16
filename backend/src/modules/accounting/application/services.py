"""Application services (use-case orchestration) for Accounting, Phase 8 §2."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from src.modules.accounting.domain.entities import (
    ACCOUNT_TYPES,
    EntryNotDraftError,
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
    CostCenter,
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
    CostCenterRepository,
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
    # P0-5 (3-Day Brief): Fixed Assets register accounts, seeded for every
    # newly bootstrapped company; migration a4b5c6d7e8f9 backfills these
    # into companies that already existed when this module shipped.
    ("1400", "Fixed Assets", "الأصول الثابتة", "asset", "1000"),
    ("1410", "Property, Plant & Equipment", "الممتلكات والمعدات", "asset", "1400"),
    ("1490", "Accumulated Depreciation", "مجمع الإهلاك", "asset", "1400"),
    ("2000", "Liabilities", "Liabilities AR", "liability", None),
    ("2100", "Accounts Payable", "Accounts Payable AR", "liability", "2000"),
    ("2200", "VAT Payable", "VAT Payable AR", "liability", "2000"),
    ("2300", "Goods Received Not Invoiced", "GRNI AR", "liability", "2000"),
    ("3000", "Equity", "Equity AR", "equity", None),
    ("3100", "Owner's Capital", "Owner's Capital AR", "equity", "3000"),
    ("3200", "Retained Earnings", "Retained Earnings AR", "equity", "3000"),
    ("4000", "Revenue", "Revenue AR", "revenue", None),
    ("4100", "Sales Revenue", "Sales Revenue AR", "revenue", "4000"),
    ("4900", "Gain on Disposal of Fixed Assets", "أرباح استبعاد الأصول الثابتة", "revenue", "4000"),
    ("5000", "Expenses", "Expenses AR", "expense", None),
    ("5100", "Cost of Goods Sold", "COGS AR", "expense", "5000"),
    ("5200", "Operating Expenses", "Operating Expenses AR", "expense", "5000"),
    ("5900", "Loss on Disposal of Fixed Assets", "خسائر استبعاد الأصول الثابتة", "expense", "5000"),
    ("5950", "Depreciation Expense", "مصروف الإهلاك", "expense", "5000"),
]


# P0-4 (3-Day Brief): a Chart of Accounts may not go deeper than 4 levels.
MAX_ACCOUNT_LEVEL = 4


class _Unset:
    """Sentinel distinguishing "parent_id not provided" (leave unchanged)
    from "parent_id explicitly set to None" (move to root) in
    ChartOfAccountsService.update_account's keyword-only signature."""


_UNSET = _Unset()


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
                level=parent.level + 1 if parent else 1,
            )
            await self.account_repo.add(account)
            if parent is not None and not parent.is_group:
                parent.is_group = True
                await self.account_repo.update(parent)
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
        is_group: bool = False,
    ) -> Account:
        if account_type_code not in ACCOUNT_TYPES:
            raise ValueError(f"Unknown account type: {account_type_code}")
        existing = await self.account_repo.get_by_code(company_id, code)
        if existing is not None:
            raise ValueError(f"Account code already exists: {code}")

        parent: Account | None = None
        level = 1
        if parent_id is not None:
            parent = await self.account_repo.get_by_id(parent_id)
            if parent is None or parent.company_id != company_id:
                raise ValueError("Parent account not found in this company")
            level = parent.level + 1
            if level > MAX_ACCOUNT_LEVEL:
                raise ValueError(
                    f"Cannot create account: parent {parent.code} is already at level "
                    f"{parent.level}, a 4th-level maximum would be exceeded"
                )

        account_type = await self.account_type_repo.get_by_code(account_type_code)
        account = Account(
            id=uuid.uuid4(),
            company_id=company_id,
            code=code,
            name=name,
            name_ar=name_ar,
            account_type_id=account_type.id,
            parent_id=parent_id,
            level=level,
            is_group=is_group,
        )
        await self.account_repo.add(account)

        # An account with children is a header/category by definition and
        # can never be posted to directly -- promote the parent the moment
        # it gains its first child rather than leaving that invariant to
        # the caller (mirrors "auto-compute level from parent").
        if parent is not None and not parent.is_group:
            parent.is_group = True
            await self.account_repo.update(parent)

        return account

    async def update_account(
        self,
        *,
        account_id: UUID,
        company_id: UUID,
        code: str | None = None,
        name: str | None = None,
        name_ar: str | None = None,
        account_type_code: str | None = None,
        parent_id: UUID | None | _Unset = _UNSET,
        is_group: bool | None = None,
        is_active: bool | None = None,
    ) -> Account:
        account = await self.account_repo.get_by_id(account_id)
        if account is None or account.company_id != company_id:
            raise ValueError("Account not found")

        if code is not None and code != account.code:
            existing = await self.account_repo.get_by_code(company_id, code)
            if existing is not None and existing.id != account.id:
                raise ValueError(f"Account code already exists: {code}")
            account.code = code

        if name is not None:
            account.name = name
        if name_ar is not None:
            account.name_ar = name_ar
        if account_type_code is not None:
            if account_type_code not in ACCOUNT_TYPES:
                raise ValueError(f"Unknown account type: {account_type_code}")
            account_type = await self.account_type_repo.get_by_code(account_type_code)
            account.account_type_id = account_type.id
        if is_active is not None:
            account.is_active = is_active

        has_children = await self.account_repo.has_children(account.id)
        if is_group is not None:
            if is_group is False and has_children:
                raise ValueError("Cannot mark an account with sub-accounts as a posting account")
            account.is_group = is_group

        if parent_id is not _UNSET and parent_id != account.parent_id:
            if parent_id == account.id:
                raise ValueError("An account cannot be its own parent")
            new_parent: Account | None = None
            new_level = 1
            if parent_id is not None:
                new_parent = await self.account_repo.get_by_id(parent_id)
                if new_parent is None or new_parent.company_id != company_id:
                    raise ValueError("Parent account not found in this company")
                # Cycle check: walk up from the proposed new parent -- if we
                # ever reach `account` itself, this reparent would create a
                # loop (moving an account underneath its own descendant).
                ancestor = new_parent
                while ancestor is not None:
                    if ancestor.id == account.id:
                        raise ValueError("Cannot move an account under its own descendant")
                    ancestor = (
                        await self.account_repo.get_by_id(ancestor.parent_id)
                        if ancestor.parent_id
                        else None
                    )
                new_level = new_parent.level + 1

            # Moving a subtree shifts every descendant's level too --
            # compute the full new depth before committing to anything, so
            # a reparent that would push a great-grandchild past level 4 is
            # rejected outright instead of applied and truncated.
            deepest = await self._deepest_descendant_offset(account.id)
            if new_level + deepest > MAX_ACCOUNT_LEVEL:
                raise ValueError(
                    f"Cannot move {account.code} here: a descendant would exceed "
                    f"{MAX_ACCOUNT_LEVEL} levels"
                )

            account.parent_id = parent_id
            await self._recompute_subtree_levels(account, new_level)

            # An old parent that just lost its last child is left as
            # is_group=True -- it's free to become a posting account again,
            # but only via an explicit is_group=False on a separate update,
            # not silently flipped back as a side effect of this move.
            if new_parent is not None and not new_parent.is_group:
                new_parent.is_group = True
                await self.account_repo.update(new_parent)

        return await self.account_repo.update(account)

    async def delete_account(self, *, account_id: UUID, company_id: UUID) -> None:
        account = await self.account_repo.get_by_id(account_id)
        if account is None or account.company_id != company_id:
            raise ValueError("Account not found")
        if await self.account_repo.has_children(account.id):
            raise ValueError(f"Cannot delete {account.code}: it has sub-accounts")
        if await self.account_repo.has_transactions(account.id):
            raise ValueError(f"Cannot delete {account.code}: it has posted transactions")
        account.deleted_at = _utcnow_naive()
        await self.account_repo.update(account)

    async def _deepest_descendant_offset(self, account_id: UUID) -> int:
        """0 if the account has no children, 1 if its deepest descendant is
        a direct child, 2 for a grandchild, etc."""
        children = await self.account_repo.list_children(account_id)
        if not children:
            return 0
        return 1 + max([await self._deepest_descendant_offset(c.id) for c in children])

    async def _recompute_subtree_levels(self, account: Account, new_level: int) -> None:
        account.level = new_level
        await self.account_repo.update(account)
        for child in await self.account_repo.list_children(account.id):
            await self._recompute_subtree_levels(child, new_level + 1)


class CostCenterService:
    """Standard SME ERP Phase 1 -- Cost Centers. Archive, never delete
    (mirrors ChartOfAccountsService's Account.is_active pattern exactly):
    a cost center once referenced by a real journal_entry_line must never
    disappear, so there is deliberately no delete_cost_center method."""

    def __init__(self, cost_center_repo: CostCenterRepository):
        self.cost_center_repo = cost_center_repo

    async def create_cost_center(
        self, *, company_id: UUID, name: str, name_ar: str | None = None
    ) -> CostCenter:
        name = name.strip()
        if not name:
            raise ValueError("Cost center name is required")
        existing = await self.cost_center_repo.get_by_name(company_id, name)
        if existing is not None:
            raise ValueError(f"A cost center named '{name}' already exists")
        cost_center = CostCenter(id=uuid.uuid4(), company_id=company_id, name=name, name_ar=name_ar)
        return await self.cost_center_repo.add(cost_center)

    async def update_cost_center(
        self,
        *,
        cost_center_id: UUID,
        company_id: UUID,
        name: str | None = None,
        name_ar: str | None = None,
        is_active: bool | None = None,
    ) -> CostCenter:
        cost_center = await self.cost_center_repo.get_by_id(company_id, cost_center_id)
        if cost_center is None:
            raise ValueError("Cost center not found")

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("Cost center name is required")
            if name.lower() != cost_center.name.lower():
                existing = await self.cost_center_repo.get_by_name(company_id, name)
                if existing is not None and existing.id != cost_center.id:
                    raise ValueError(f"A cost center named '{name}' already exists")
            cost_center.name = name
        if name_ar is not None:
            cost_center.name_ar = name_ar
        if is_active is not None:
            cost_center.is_active = is_active

        return await self.cost_center_repo.update(cost_center)


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
        cost_center_repo: CostCenterRepository | None = None,
    ):
        self.entry_repo = entry_repo
        self.journal_repo = journal_repo
        self.account_repo = account_repo
        self.period_repo = period_repo
        # Optional (default None) purely so every existing call site that
        # doesn't touch cost centers keeps working unchanged -- a company
        # with zero cost centers must be able to post journal entries
        # exactly as before Standard SME ERP Phase 1 shipped.
        self.cost_center_repo = cost_center_repo

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
        description: str | None = None,
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
            if account.is_group:
                raise ValueError(
                    f"Cannot post to {account.code} — {account.name}: it is a group account "
                    "(has sub-accounts); post to one of its sub-accounts instead"
                )
            # Standard SME ERP Phase 1: cost_center_id has been a real FK on
            # journal_entry_line since the M1 schema, but nothing ever
            # validated it belonged to this company or was still active
            # (no CostCenter could even be created before this stage).
            # cost_center_repo is None for every caller that never touches
            # cost centers (Sales/Purchasing/Payments/Fixed Assets
            # auto-posting) -- validation only runs where a caller actually
            # supplies both the repo and a line-level cost_center_id.
            if line.cost_center_id is not None and self.cost_center_repo is not None:
                cost_center = await self.cost_center_repo.get_by_id(company_id, line.cost_center_id)
                if cost_center is None:
                    raise ValueError(f"Cost center not found in this company: {line.cost_center_id}")
                if not cost_center.is_active:
                    raise ValueError(f"Cost center is archived and cannot be used: {cost_center.name}")

        orm_entry = JournalEntry(
            id=domain_entry.id,
            company_id=company_id,
            branch_id=branch_id,
            journal_id=journal.id,
            entry_date=entry_date,
            reference=reference,
            description=description,
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
        if entry.status != "draft":
            raise PostedEntryImmutableError(f"This entry is {entry.status} and cannot be posted")

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

    async def cancel_draft_entry(self, *, entry_id: UUID, company_id: UUID) -> JournalEntry:
        """A draft has zero ledger impact until posted, so cancelling one is
        never blocked by fiscal period status — unlike post_entry, there is
        deliberately no period_repo check here."""
        entry = await self.entry_repo.get_by_id(entry_id)
        if entry is None or entry.company_id != company_id:
            raise ValueError("Journal entry not found")
        if entry.status != "draft":
            raise EntryNotDraftError(f"Only a draft entry can be cancelled (this entry is {entry.status})")

        entry.status = "cancelled"
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
        self,
        *,
        company_id: UUID,
        date_from: date,
        date_to: date,
        branch_id: UUID | None = None,
        detail_level: int | None = None,
    ) -> list[dict]:
        rows = await self.entry_repo.trial_balance(company_id, date_from, date_to, branch_id)
        if detail_level is None or not rows:
            return rows
        accounts_by_id = await self._accounts_by_id(company_id)
        sum_fields = ("opening_balance", "period_debit", "period_credit", "closing_balance", "total_debit", "total_credit")
        return self._rollup_rows(rows, accounts_by_id, detail_level, sum_fields)

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
        self,
        *,
        company_id: UUID,
        date_from: date,
        date_to: date,
        branch_id: UUID | None = None,
        detail_level: int | None = None,
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

        if detail_level is not None:
            accounts_by_id = await self._accounts_by_id(company_id)
            revenue_accounts = self._rollup_rows(revenue_accounts, accounts_by_id, detail_level, ("amount",))
            cogs_accounts = self._rollup_rows(cogs_accounts, accounts_by_id, detail_level, ("amount",))
            opex_accounts = self._rollup_rows(opex_accounts, accounts_by_id, detail_level, ("amount",))

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
        self,
        *,
        company_id: UUID,
        as_of_date: date,
        branch_id: UUID | None = None,
        detail_level: int | None = None,
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

        if detail_level is not None:
            accounts_by_id = await self._accounts_by_id(company_id)
            assets = self._rollup_rows(assets, accounts_by_id, detail_level, ("amount",))
            liabilities = self._rollup_rows(liabilities, accounts_by_id, detail_level, ("amount",))
            equity = self._rollup_rows(equity, accounts_by_id, detail_level, ("amount",))

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

    async def _accounts_by_id(self, company_id: UUID) -> dict[UUID, Account]:
        """P0-4 follow-up (Owner request): a "detail level" selector for
        Trial Balance / Income Statement / Balance Sheet, so a coarser
        level rolls several posting accounts up into their shared
        ancestor instead of always listing every leaf account. Loaded
        once per report call and reused for every row's ancestor walk."""
        if self.account_repo is None:
            return {}
        accounts = await self.account_repo.list_by_company(company_id)
        return {a.id: a for a in accounts}

    @staticmethod
    def _rollup_ancestor(
        account_id: UUID, accounts_by_id: dict[UUID, Account], target_level: int
    ) -> Account | None:
        """Walk up the parent chain from account_id until reaching an
        account at or above (numerically <=) target_level -- that
        account is what every deeper descendant's activity rolls up
        into. Returns None only if account_id itself is unknown (should
        never happen for a row the DB itself just returned)."""
        current = accounts_by_id.get(account_id)
        if current is None:
            return None
        while current.level > target_level and current.parent_id is not None:
            parent = accounts_by_id.get(current.parent_id)
            if parent is None:
                break
            current = parent
        return current

    def _rollup_rows(
        self,
        rows: list[dict],
        accounts_by_id: dict[UUID, Account],
        target_level: int,
        sum_fields: tuple[str, ...],
    ) -> list[dict]:
        """Groups `rows` (each carrying account_id/account_code/
        account_name plus whatever Decimal fields `sum_fields` names) by
        each row's rollup ancestor at target_level, summing those fields.
        Generic across Trial Balance's multi-column shape and the
        single "amount" column Income Statement/Balance Sheet rows use."""
        grouped: dict[UUID, dict] = {}
        order: list[UUID] = []
        for row in rows:
            ancestor = self._rollup_ancestor(row["account_id"], accounts_by_id, target_level)
            key = ancestor.id if ancestor is not None else row["account_id"]
            if key not in grouped:
                grouped[key] = {
                    **row,
                    "account_id": key,
                    "account_code": ancestor.code if ancestor is not None else row["account_code"],
                    "account_name": ancestor.name if ancestor is not None else row["account_name"],
                    **{f: Decimal("0") for f in sum_fields},
                }
                order.append(key)
            for f in sum_fields:
                grouped[key][f] += row[f]
        return [grouped[k] for k in sorted(order, key=lambda k: grouped[k]["account_code"])]


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
