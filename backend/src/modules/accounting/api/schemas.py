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
    is_active: bool

    model_config = {"from_attributes": True}


class AccountCreateRequest(BaseModel):
    code: str
    name: str
    name_ar: str | None = None
    account_type_code: str = Field(pattern="^(asset|liability|equity|revenue|expense)$")
    parent_id: UUID | None = None


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
    status: str

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
    total_debit: Decimal
    total_credit: Decimal


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
