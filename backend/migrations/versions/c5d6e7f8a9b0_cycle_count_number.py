"""cycle count document number

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-21 00:00:00.000000

Owner request: a Cycle Count reads as its own distinct document type in
the ledger (a real number, like every other document -- Sales Invoice,
Purchase Order, Vendor Bill, Debit/Credit Note) instead of a raw UUID
stuffed into a journal entry's reference field. Adds `cycle_count.number`
(CC-###### prefix, same shape as every other document series in this
codebase) and backfills every existing row -- ordered by scheduled_date
then id for a stable, deterministic sequence, since there is no
created_at column on this table to order by instead.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cycle_count", sa.Column("number", sa.Text(), nullable=True))

    # Bulk cross-company backfill with no app.current_company_id set --
    # same NO FORCE/FORCE bracket every other bulk backfill migration in
    # this codebase uses (e.g. c9f1a2b3d4e5), otherwise RLS silently
    # scopes the UPDATE to zero rows instead of erroring.
    op.execute("ALTER TABLE cycle_count NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        WITH numbered AS (
            SELECT id, 'CC-' || LPAD(
                ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY scheduled_date, id)::text, 6, '0'
            ) AS generated_number
            FROM cycle_count
        )
        UPDATE cycle_count
        SET number = numbered.generated_number
        FROM numbered
        WHERE cycle_count.id = numbered.id
        """
    )
    op.execute("ALTER TABLE cycle_count FORCE ROW LEVEL SECURITY")

    op.alter_column("cycle_count", "number", nullable=False)
    op.create_index(
        "ix_cycle_count_company_number", "cycle_count", ["company_id", "number"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_cycle_count_company_number", table_name="cycle_count")
    op.drop_column("cycle_count", "number")
