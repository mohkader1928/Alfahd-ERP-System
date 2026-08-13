"""journal entry cancelled status

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-08-13 00:00:00.000000

Owner-reported gap: a draft journal entry created inside a fiscal period
that later gets closed has no way out — it can't be posted (period
closed, correctly), and there was no way to edit or cancel it either.
A draft has zero ledger impact until posted, so cancelling one should
never depend on fiscal period status. Adds 'cancelled' as a fourth
allowed status alongside draft/posted/reversed.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'b6c7d8e9f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_journal_entry_status", "journal_entry", type_="check")
    op.create_check_constraint(
        "ck_journal_entry_status",
        "journal_entry",
        "status IN ('draft','posted','reversed','cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_journal_entry_status", "journal_entry", type_="check")
    op.create_check_constraint(
        "ck_journal_entry_status",
        "journal_entry",
        "status IN ('draft','posted','reversed')",
    )
