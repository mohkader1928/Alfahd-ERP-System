"""Pure domain types for Inventory (Phase 8 §2)."""

from __future__ import annotations

from src.shared.domain.base_entity import DomainError

MOVE_TYPES = ("receipt", "delivery", "transfer", "adjustment")


class InsufficientStockError(DomainError):
    """FR-INV-007: an item's balance at a location may not go negative
    without an explicit override."""
