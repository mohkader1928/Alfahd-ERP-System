"""cost_center: name_ar, is_active, created_at (Standard SME ERP Phase 1)

Revision ID: a66bf7a6649e
Revises: 84934dc970fa
Create Date: 2026-08-16 00:00:00.000000

CostCenter has existed since the M1 Accounting migration (schema
placeholder + journal_entry_line.cost_center_id FK, both already RLS'd
under company_isolation since 461205cf56a6) but has never had a real
management surface. This adds only what a real, non-destructively
archivable capability needs: name_ar (Arabic-first, matching Account/
Partner/Product/Branch/Warehouse), is_active (archive, never delete —
existing journal_entry_line.cost_center_id references must never be
orphaned), and created_at (matches every other accounting master-data
table's audit-trail expectations). Purely additive; existing rows get
is_active=true (server default), matching current behavior for the
handful of cost centers, if any, already sitting in this column-only
table (none were ever creatable via any API before this migration).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a66bf7a6649e"
down_revision: Union[str, None] = "84934dc970fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cost_center", sa.Column("name_ar", sa.Text(), nullable=True))
    op.add_column(
        "cost_center", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"))
    )
    op.add_column(
        "cost_center", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()"))
    )


def downgrade() -> None:
    op.drop_column("cost_center", "created_at")
    op.drop_column("cost_center", "is_active")
    op.drop_column("cost_center", "name_ar")
