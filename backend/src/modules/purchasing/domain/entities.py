"""Pure domain types for Purchasing (Phase 8 §2)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.shared.domain.base_entity import DomainError

DOC_STATUSES = ("draft", "confirmed", "done", "cancelled")
BILL_STATUSES = ("draft", "matched", "mismatched", "approved", "posted")


class ThreeWayMatchError(DomainError):
    """FR-PUR-003: a Vendor Bill's quantities/prices don't reconcile against
    the Purchase Order and Goods Receipt."""


@dataclass(frozen=True)
class MatchLine:
    product_id: object
    po_qty: Decimal
    po_unit_price: Decimal
    received_qty: Decimal
    bill_qty: Decimal
    bill_unit_price: Decimal


def check_three_way_match(lines: list[MatchLine], *, price_tolerance_percent: Decimal = Decimal("0")) -> list[str]:
    """Returns a list of human-readable mismatch reasons (empty = matched).
    Pure function — no I/O, testable without a database."""
    errors: list[str] = []
    for line in lines:
        if line.bill_qty > line.received_qty:
            errors.append(
                f"Product {line.product_id}: billed qty {line.bill_qty} exceeds received qty {line.received_qty}"
            )
        if line.bill_qty > line.po_qty:
            errors.append(f"Product {line.product_id}: billed qty {line.bill_qty} exceeds PO qty {line.po_qty}")

        if price_tolerance_percent > 0 and line.po_unit_price > 0:
            allowed_delta = line.po_unit_price * price_tolerance_percent / Decimal("100")
            if abs(line.bill_unit_price - line.po_unit_price) > allowed_delta:
                errors.append(
                    f"Product {line.product_id}: billed price {line.bill_unit_price} differs from PO price "
                    f"{line.po_unit_price} beyond {price_tolerance_percent}% tolerance"
                )
        elif line.bill_unit_price != line.po_unit_price:
            errors.append(
                f"Product {line.product_id}: billed price {line.bill_unit_price} != PO price {line.po_unit_price}"
            )
    return errors
