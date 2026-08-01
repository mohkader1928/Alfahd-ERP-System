from decimal import Decimal

from src.modules.inventory.domain.entities import InsufficientStockError
from src.modules.inventory.domain.valuation.strategy import IssueResult, IValuationStrategy, Layer


class AverageValuationStrategy(IValuationStrategy):
    """Issues at the current moving average cost (FR-INV-004). Availability
    (FR-INV-007) is still checked — Average just doesn't consume discrete
    layers, so the check is against total on-hand qty, passed in via the
    `layers` list's aggregate for simplicity (a single synthetic layer)."""

    def compute_issue_cost(
        self, qty_to_issue: Decimal, *, layers: list[Layer], moving_avg_cost: Decimal
    ) -> IssueResult:
        available = sum((layer.qty_remaining for layer in layers), Decimal("0"))
        if qty_to_issue > available:
            raise InsufficientStockError(
                f"Insufficient stock: requested {qty_to_issue}, available {available}"
            )
        total_cost = (qty_to_issue * moving_avg_cost).quantize(Decimal("0.0001"))
        return IssueResult(total_cost=total_cost, unit_cost=moving_avg_cost, consumed=[])
