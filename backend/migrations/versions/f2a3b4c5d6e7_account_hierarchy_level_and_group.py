"""chart of accounts: level + group-posting status

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-09 00:00:00.000003

P0-4 (3-Day Brief): Chart of Accounts restricted to 4 levels, with an
explicit level column (auto-computed from parent going forward, not
derived on every read) and a group-posting flag so a header/category
account (one with children) can be blocked from receiving journal
entry postings directly -- only its leaf descendants should ever be
posted to.

Backfill: `level` is computed via a recursive walk from each root
account (parent_id IS NULL) down, matching however deep the existing
tree already goes (the seeded default CoA is 2 levels, but this isn't
assumed). `is_group` is derived from the data itself: any account
that is *referenced* as another account's parent_id is, by
definition, a header account with children -- exactly matches the 5
top-level categories (Assets/Liabilities/Equity/Revenue/Expenses) in
the seeded default CoA, none of which are ever posted to directly
anywhere in the codebase.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("account", sa.Column("level", sa.SmallInteger(), nullable=False, server_default="1"))
    op.add_column("account", sa.Column("is_group", sa.Boolean(), nullable=False, server_default="false"))
    op.create_check_constraint("ck_account_level_range", "account", "level BETWEEN 1 AND 4")

    op.execute("ALTER TABLE account NO FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        WITH RECURSIVE acc_level AS (
            SELECT id, 1 AS level FROM account WHERE parent_id IS NULL
            UNION ALL
            SELECT a.id, al.level + 1 FROM account a JOIN acc_level al ON a.parent_id = al.id
        )
        UPDATE account SET level = acc_level.level
        FROM acc_level WHERE account.id = acc_level.id
        """
    )
    op.execute(
        """
        UPDATE account SET is_group = true
        WHERE id IN (SELECT DISTINCT parent_id FROM account WHERE parent_id IS NOT NULL)
        """
    )

    op.execute("ALTER TABLE account FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_constraint("ck_account_level_range", "account", type_="check")
    op.drop_column("account", "is_group")
    op.drop_column("account", "level")
