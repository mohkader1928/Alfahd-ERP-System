from decimal import Decimal

from src.modules.inventory.domain.entities import InsufficientStockError
from src.modules.inventory.domain.valuation.strategy import IssueResult, IValuationStrategy, Layer


class FifoValuationStrategy(IValuationStrategy):
    """Consumes the oldest layers first (FR-INV-004)."""

    def compute_issue_cost(
        self, qty_to_issue: Decimal, *, layers: list[Layer], moving_avg_cost: Decimal
    ) -> IssueResult:
        remaining = qty_to_issue
        total_cost = Decimal("0")
        consumed: list[tuple] = []

        for layer in sorted(layers, key=lambda entry: entry.received_at):
            if remaining <= 0:
                break
            take = min(layer.qty_remaining, remaining)
            if take <= 0:
                continue
            total_cost += take * layer.unit_cost
            consumed.append((layer.id, take))
            remaining -= take

        if remaining > 0:
            raise InsufficientStockError(
                f"Insufficient stock: {remaining} unit(s) short of the requested {qty_to_issue}"
            )

        # Quantized to the unit_cost column's actual scale (NUMERIC(18,4) —
        # Phase 7 §5): division otherwise retains full precision in Python
        # (e.g. "5.5000000000"), which is fine in the DB (Postgres rounds to
        # the column scale on storage) but leaks as a mismatch when the
        # in-memory object is returned directly in an API response without
        # a round-trip SELECT — same class of bug fixed in Sales (M2).
        unit_cost = (total_cost / qty_to_issue).quantize(Decimal("0.0001")) if qty_to_issue > 0 else Decimal("0")
        return IssueResult(total_cost=total_cost, unit_cost=unit_cost, consumed=consumed)
