"""Commercial Performance Stage 3 — commission ledger.

`CommissionTransaction` mirrors `JournalEntry`'s own `source_table`/
`source_id` polymorphic-reference convention
(`accounting/infrastructure/models.py`), applied to a new concern: one
immutable row per commission-bearing event (an issued sales invoice, a
credit note reversing part of one, or a customer payment). Never mutated
once written — a credit note creates a NEW negative-signed row rather than
editing the original invoice's row, the same reversal-not-mutation
philosophy `JournalEntry.reversed_entry_id` already uses. `commission_rate`
is stored on every row precisely so a later rate change on
`SalesRepresentative.commission_rate` can never retroactively alter a
historical commission figure.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.infrastructure.db.base import Base

COMMISSION_TYPES = ("sales", "collection")
COMMISSION_STATUSES = ("calculated", "approved", "paid", "cancelled")


class CommissionTransaction(Base):
    __tablename__ = "commission_transaction"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    representative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_representative.id"), nullable=False
    )
    commission_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Polymorphic reference, same shape as JournalEntry.source_table/source_id.
    # 'sales_invoice' covers both a forward invoice and a credit note (they
    # are the same table, distinguished by invoice_type); 'payment' covers a
    # customer receipt.
    source_table: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The commercial amount commission was computed on (pre-tax subtotal for
    # sales, the collected amount for collections). Negative for a
    # credit-note reversal row.
    base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # Historical snapshot of SalesRepresentative.commission_rate at the
    # moment this row was written — never re-read later.
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    transaction_date: Mapped[date] = mapped_column(nullable=False)
    # Forward-compatibility for a future settlement stage (not built here —
    # no endpoint in this stage ever writes anything but 'calculated').
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'calculated'"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        CheckConstraint(f"commission_type IN {COMMISSION_TYPES}", name="ck_commission_transaction_type"),
        CheckConstraint(f"status IN {COMMISSION_STATUSES}", name="ck_commission_transaction_status"),
        Index("ix_commission_transaction_source", "source_table", "source_id"),
        Index(
            "ix_commission_transaction_company_rep_date",
            "company_id",
            "representative_id",
            "transaction_date",
        ),
    )
