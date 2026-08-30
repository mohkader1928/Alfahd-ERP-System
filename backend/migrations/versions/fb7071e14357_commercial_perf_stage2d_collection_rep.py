"""Commercial Performance Stage 2D — collection representative on Payment

Revision ID: fb7071e14357
Revises: 656ce42660aa
Create Date: 2026-08-30 00:00:00.000000

Purely additive, approved Stage 2D scope only:

One new nullable FK column, `payment.collection_rep_id`, referencing
`sales_representative.id` (Stage 2A). Deliberately independent from
`sales_invoice.sales_rep_id` — the person who sells is not necessarily
the person who collects, and this must never be derived from the
invoice(s) a payment settles. No new table, no RLS change — `payment`
already carries the `company_isolation` policy from its own original
migration.

Applies conceptually to customer receipts (payment_type = 'customer');
no business requirement was identified for vendor payments, so the
column is simply left unused/NULL for that side rather than adding
type-conditional constraints.

No backfill: every existing payment keeps collection_rep_id = NULL
("Unattributed / Legacy"), so all existing records and workflows keep
working unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'fb7071e14357'
down_revision: Union[str, None] = '656ce42660aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment",
        sa.Column(
            "collection_rep_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_representative.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("payment", "collection_rep_id")
