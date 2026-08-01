"""IValuationStrategy — Strategy pattern (Phase 8 §7), selected per company's
`valuation_method`. Pure computation over plain data, no DB access — the
application layer fetches layers/quant state and persists the result,
keeping this testable without a database.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class Layer:
    id: UUID
    qty_remaining: Decimal
    unit_cost: Decimal
    received_at: datetime


@dataclass(frozen=True)
class IssueResult:
    total_cost: Decimal
    unit_cost: Decimal
    consumed: list[tuple[UUID, Decimal]]  # (layer_id, qty_consumed) — empty for Average


class IValuationStrategy(ABC):
    @abstractmethod
    def compute_issue_cost(
        self, qty_to_issue: Decimal, *, layers: list[Layer], moving_avg_cost: Decimal
    ) -> IssueResult: ...
