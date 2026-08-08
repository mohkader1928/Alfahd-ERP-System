"""journal entry header description

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-08 00:00:00.000001

Owner-requested: a manual Journal Entry had a per-line description
(journal_entry_line.description) but no field to record what the entry
as a whole is for - every reference ERP has a header-level narration on
a manual journal entry, distinct from each line's own memo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("journal_entry", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("journal_entry", "description")
