"""Pure domain entities for Accounting (Phase 8 §2 — no ORM/HTTP imports)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from src.shared.domain.base_entity import DomainError

ACCOUNT_TYPES = ("asset", "liability", "equity", "revenue", "expense")
TAX_KINDS = ("standard", "zero_rated", "exempt", "out_of_scope")


class UnbalancedEntryError(DomainError):
    """Raised when a journal entry's total debit != total credit (FR-ACC-003)."""


class PostedEntryImmutableError(DomainError):
    """Raised when attempting to edit a Posted journal entry (FR-ACC-004)."""


class PeriodClosedError(DomainError):
    """Raised when attempting to post into a closed fiscal period (FR-ACC-011)."""


class EntryNotDraftError(DomainError):
    """Raised when a draft-only operation (cancel) targets a non-draft entry."""


@dataclass
class JournalEntryLine:
    account_id: UUID
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    cost_center_id: UUID | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if self.debit < 0 or self.credit < 0:
            raise DomainError("debit/credit cannot be negative")
        if self.debit > 0 and self.credit > 0:
            raise DomainError("a line cannot be both debit and credit")


@dataclass
class JournalEntry:
    """Aggregate root. `assert_balanced()` is the domain-layer mirror of the
    DB's deferred constraint trigger (Phase 7 §1.6) — checked before the
    trigger ever runs, so the client gets a clean 422 instead of a raw
    constraint-violation error on commit.
    """

    id: UUID
    company_id: UUID
    journal_id: UUID
    lines: list[JournalEntryLine] = field(default_factory=list)
    status: str = "draft"

    @property
    def total_debit(self) -> Decimal:
        return sum((line.debit for line in self.lines), Decimal("0"))

    @property
    def total_credit(self) -> Decimal:
        return sum((line.credit for line in self.lines), Decimal("0"))

    def assert_balanced(self) -> None:
        if len(self.lines) < 2:
            raise UnbalancedEntryError("a journal entry needs at least two lines")
        if self.total_debit != self.total_credit:
            raise UnbalancedEntryError(
                f"total debit ({self.total_debit}) does not equal total credit ({self.total_credit})"
            )

    def assert_mutable(self) -> None:
        if self.status == "posted":
            raise PostedEntryImmutableError(
                "a posted journal entry cannot be modified; reverse it instead"
            )


@dataclass
class TaxCalculationResult:
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


def calculate_tax(
    *, line_amount: Decimal, tax_kind: str, rate_percent: Decimal
) -> TaxCalculationResult:
    """Domain service — FR-ACC-007 tax engine core (Strategy-free since KSA
    VAT is a flat-percentage model; a compound Tax Group sums this per rate).
    """
    if tax_kind not in TAX_KINDS:
        raise DomainError(f"Unknown tax kind: {tax_kind}")
    if tax_kind in ("zero_rated", "exempt", "out_of_scope"):
        tax_amount = Decimal("0")
    else:
        tax_amount = (line_amount * rate_percent / Decimal("100")).quantize(Decimal("0.01"))
    return TaxCalculationResult(
        taxable_amount=line_amount, tax_amount=tax_amount, total_amount=line_amount + tax_amount
    )
