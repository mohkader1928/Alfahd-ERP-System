"""Pure domain types for Payments (Phase 17D)."""

from __future__ import annotations

from src.shared.domain.base_entity import DomainError

PAYMENT_TYPES = ("customer", "vendor")


class OverAllocationError(DomainError):
    """An allocation may not exceed the payment's remaining unallocated
    amount, nor the target invoice/bill's remaining outstanding balance."""


class InvalidAllocationTargetError(DomainError):
    """A customer payment must allocate only to sales invoices; a vendor
    payment must allocate only to vendor bills — never mixed, and never to
    a document belonging to a different partner than the payment."""
