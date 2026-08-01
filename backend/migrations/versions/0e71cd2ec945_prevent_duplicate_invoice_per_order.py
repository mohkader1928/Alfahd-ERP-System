"""phase 16b-implementation-01 — prevent duplicate invoice per sales order

Revision ID: 0e71cd2ec945
Revises: 8957d3c39d54
Create Date: 2026-08-01 12:00:00.000000

Root cause (docs/16b-idempotency-concurrency-design.md, Critical Race
Condition #1): `issue_invoice_from_order` reads `sales_order.status` but
never writes it, so retrying `POST /orders/{id}:invoice` — sequentially
or concurrently — creates a second SalesInvoice, journal entry, ZATCA
submission, and stock deduction every time.

The natural business invariant this nucleus already assumes (whole-order
invoicing, no partial invoicing, no standalone Delivery document — see
Phase 8 §3 / M2 kickoff scope note) is: **at most one invoice can be
linked to a given sales order.** `sales_invoice.sales_order_id` is
nullable (credit notes and any invoice not created from an order leave it
NULL), so a plain UNIQUE constraint would incorrectly forbid multiple
NULLs — a partial unique index scoped to `WHERE sales_order_id IS NOT
NULL` expresses the actual invariant precisely.

This is a database-level guarantee, not just an application check: two
concurrent transactions racing to INSERT a SalesInvoice for the same
sales_order_id will have the second one fail atomically at the database
layer regardless of timing, closing the race completely — no explicit
lock is needed because Postgres's unique index enforcement is itself the
concurrency-safe mechanism here.

Verified before creating this constraint: zero existing sales_invoice
rows share a sales_order_id (173 non-null rows checked, 0 violations) —
see the verification report for the exact query and output. No cleanup
was needed.

Purely additive: no existing column, data, or other constraint is
touched.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0e71cd2ec945'
down_revision: Union[str, None] = '8957d3c39d54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX ux_sales_invoice_sales_order_id
        ON sales_invoice (sales_order_id)
        WHERE sales_order_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_sales_invoice_sales_order_id")
