"""Commercial Performance Stage 1 — customer/vendor credit management fields

Revision ID: 625530a27ae2
Revises: 744d11736e39
Create Date: 2026-08-30 00:00:00.000000

Purely additive: three new nullable columns on `partner`.

`credit_limit`/`credit_days` govern the customer side; `vendor_credit_days`
is kept as a separate field (not shared with `credit_days`) because a single
Partner row can be both customer and vendor with different terms in each
direction. The existing `payment_terms` freeform text column is untouched —
it stays purely a display string, never parsed.

No backfill: every existing partner simply has NULL for all three new
columns, exactly as before this migration. No new table, no RLS change
(`partner` already has its own `company_isolation` policy).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '625530a27ae2'
down_revision: Union[str, None] = '744d11736e39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("partner", sa.Column("credit_limit", sa.Numeric(18, 4), nullable=True))
    op.add_column("partner", sa.Column("credit_days", sa.Integer(), nullable=True))
    op.add_column("partner", sa.Column("vendor_credit_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("partner", "vendor_credit_days")
    op.drop_column("partner", "credit_days")
    op.drop_column("partner", "credit_limit")
