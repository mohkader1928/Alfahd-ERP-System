"""Pydantic request/response schemas for Accounting (Phase 10 §6.2)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AccountOut(BaseModel):
    id: UUID
    company_id: UUID
    code: str
    name: str
    name_ar: str | None
    parent_id: UUID | None
    level: int
    is_group: bool
    is_active: bool
    is_cash_equivalent: bool

    model_config = {"from_attributes": True}


class CostCenterOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    name_ar: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class CostCenterCreateRequest(BaseModel):
    name: str
    name_ar: str | None = None


class CostCenterUpdateRequest(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    is_active: bool | None = None


class TaxRateOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    kind: str
    rate_percent: Decimal
    is_withholding: bool

    model_config = {"from_attributes": True}


class AccountCreateRequest(BaseModel):
    code: str
    name: str
    name_ar: str | None = None
    account_type_code: str = Field(pattern="^(asset|liability|equity|revenue|expense)$")
    parent_id: UUID | None = None
    is_group: bool = False
    is_cash_equivalent: bool = False


class AccountUpdateRequest(BaseModel):
    code: str | None = None
    name: str | None = None
    name_ar: str | None = None
    account_type_code: str | None = Field(default=None, pattern="^(asset|liability|equity|revenue|expense)$")
    parent_id: UUID | None = None
    parent_id_set: bool = False  # false = "parent_id not provided, leave unchanged"
    is_group: bool | None = None
    is_active: bool | None = None
    is_cash_equivalent: bool | None = None


class JournalEntryLineIn(BaseModel):
    account_id: UUID
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    cost_center_id: UUID | None = None
    description: str | None = None


class JournalEntryCreateRequest(BaseModel):
    journal_code: str
    entry_date: date
    reference: str | None = None
    description: str | None = None
    lines: list[JournalEntryLineIn]

    @field_validator("lines")
    @classmethod
    def at_least_two_lines(cls, v: list[JournalEntryLineIn]) -> list[JournalEntryLineIn]:
        if len(v) < 2:
            raise ValueError("a journal entry needs at least two lines")
        return v


class JournalEntryOut(BaseModel):
    id: UUID
    company_id: UUID
    journal_id: UUID
    entry_date: date
    reference: str | None
    description: str | None
    status: str
    source_table: str | None
    source_id: UUID | None

    model_config = {"from_attributes": True}


class JournalEntryLineOut(BaseModel):
    id: UUID
    account_id: UUID
    cost_center_id: UUID | None
    debit: Decimal
    credit: Decimal
    description: str | None

    model_config = {"from_attributes": True}


class JournalEntryDetailResponse(BaseModel):
    entry: JournalEntryOut
    lines: list[JournalEntryLineOut]


class TrialBalanceRow(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    account_type_code: str
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_balance: Decimal
    # Legacy aliases — kept for backward compatibility with any existing callers
    total_debit: Decimal
    total_credit: Decimal


class GeneralLedgerLine(BaseModel):
    journal_entry_id: UUID
    entry_date: date
    reference: str | None
    status: str
    debit: Decimal
    credit: Decimal
    description: str | None
    running_balance: Decimal
    source_table: str | None
    source_id: UUID | None
    cost_center_id: UUID | None = None
    cost_center_name: str | None = None


class GeneralLedgerResponse(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    opening_balance: Decimal
    lines: list[GeneralLedgerLine]
    closing_balance: Decimal


class IncomeStatementAccountRow(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    amount: Decimal


class IncomeStatementResponse(BaseModel):
    date_from: date
    date_to: date
    revenue_accounts: list[IncomeStatementAccountRow]
    revenue_total: Decimal
    cogs_accounts: list[IncomeStatementAccountRow]
    cogs_total: Decimal
    gross_profit: Decimal
    opex_accounts: list[IncomeStatementAccountRow]
    opex_total: Decimal
    operating_income: Decimal
    net_income: Decimal


class CostCenterReportAccountRow(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    type_code: str
    total_debit: Decimal
    total_credit: Decimal
    balance: Decimal


class CostCenterReportResponse(BaseModel):
    cost_center: CostCenterOut
    date_from: date
    date_to: date
    accounts: list[CostCenterReportAccountRow]
    revenue_total: Decimal
    expense_total: Decimal
    net_result: Decimal


class BalanceSheetAccountRow(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    amount: Decimal


class BalanceSheetResponse(BaseModel):
    as_of_date: date
    assets: list[BalanceSheetAccountRow]
    assets_total: Decimal
    liabilities: list[BalanceSheetAccountRow]
    liabilities_total: Decimal
    equity: list[BalanceSheetAccountRow]
    equity_total: Decimal
    current_earnings: Decimal
    total_liabilities_and_equity: Decimal


class CashFlowAccountRow(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    amount: Decimal


class CashFlowResponse(BaseModel):
    period_start: date
    period_end: date
    opening_cash: Decimal
    net_income: Decimal
    depreciation_addback: Decimal
    working_capital_lines: list[CashFlowAccountRow]
    working_capital_total: Decimal
    operating_total: Decimal
    investing_lines: list[CashFlowAccountRow]
    investing_total: Decimal
    financing_lines: list[CashFlowAccountRow]
    financing_total: Decimal
    net_change_in_cash: Decimal
    closing_cash: Decimal
    # Should always be zero -- see ReportingService.cash_flow_statement's
    # docstring for the one hand-built-JE edge case where it legitimately
    # would not be. Surfaced explicitly rather than hidden or forced to 0.
    reconciliation_difference: Decimal


class EquityLineRow(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    amount: Decimal


class EquityStatementResponse(BaseModel):
    period_start: date
    period_end: date
    opening_equity: Decimal
    profit_for_period: Decimal
    contributions: Decimal
    withdrawals: Decimal
    other_equity_lines: list[EquityLineRow]
    other_equity_total: Decimal
    closing_equity: Decimal
    # Should always be zero -- see ReportingService.statement_of_changes_in_equity's
    # docstring. Surfaced explicitly rather than hidden.
    reconciliation_difference: Decimal
    # Items the Owner's brief asked about that have no dedicated mechanism
    # in the current Chart of Accounts (e.g. "dividends") -- named here
    # rather than fabricated as a zero.
    unsupported_items: list[str]


class FiscalPeriodCreateRequest(BaseModel):
    period_start: date
    period_end: date


class FiscalPeriodOut(BaseModel):
    id: UUID
    company_id: UUID
    period_start: date
    period_end: date
    is_closed: bool

    model_config = {"from_attributes": True}
