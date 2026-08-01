"""DashboardService — Phase 8 §3: Reporting is the only module allowed to
read across other modules' repositories directly (read-only query
interfaces, not shared tables), since dashboards inherently aggregate
cross-module data (FR-RPT-003)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.modules.accounting.infrastructure.repositories import JournalEntryRepository
from src.modules.purchasing.infrastructure.repositories import VendorBillRepository
from src.modules.sales.infrastructure.repositories import SalesInvoiceRepository

ACCOUNT_CODE_AR = "1200"
ACCOUNT_CODE_AP = "2100"


@dataclass(frozen=True)
class DashboardSummary:
    period_start: date
    period_end: date
    period_sales_total: Decimal
    period_purchases_total: Decimal
    receivables_balance: Decimal
    payables_balance: Decimal


class DashboardService:
    def __init__(
        self,
        invoice_repo: SalesInvoiceRepository,
        bill_repo: VendorBillRepository,
        journal_entry_repo: JournalEntryRepository,
    ):
        self.invoice_repo = invoice_repo
        self.bill_repo = bill_repo
        self.journal_entry_repo = journal_entry_repo

    async def get_summary(self, *, company_id: UUID, period_start: date, period_end: date) -> DashboardSummary:
        sales_total = await self.invoice_repo.sum_total_in_range(company_id, period_start, period_end)
        purchases_total = await self.bill_repo.sum_total_in_range(company_id, period_start, period_end)
        # AR is a normal-debit account (asset): positive balance = amount owed to us.
        ar_balance = await self.journal_entry_repo.account_balance(company_id, ACCOUNT_CODE_AR, period_end)
        # AP is a normal-credit account (liability): flip sign for a positive "amount we owe" figure.
        ap_balance = -(await self.journal_entry_repo.account_balance(company_id, ACCOUNT_CODE_AP, period_end))

        return DashboardSummary(
            period_start=period_start,
            period_end=period_end,
            period_sales_total=sales_total,
            period_purchases_total=purchases_total,
            receivables_balance=ar_balance,
            payables_balance=ap_balance,
        )
