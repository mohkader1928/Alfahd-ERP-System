"""Account is_cash_equivalent

Standard SME ERP — Accounting Financial Statements Phase (Cash Flow
Statement, IAS 7 indirect method). Owner-approved design decision
(docs/23-cash-flow-equity-phase-a.md, decision #1, 2026-08-18): rather than
an account-code convention (fragile if a company renames/restructures its
Cash and Bank subtree), an explicit flag on `Account` is the durable
definition of "Cash and Cash Equivalents" for the new Cash Flow Statement.

Additive-only: new nullable-free boolean column, default false, backfilled
for the default seed template's `1100 Cash and Bank` subtree (root account
plus any descendants, per company) so existing companies built from
`DEFAULT_SAUDI_COA` light up correctly with zero manual work. Any other
account (a company's own bank sub-accounts, a future custom COA) can be
flagged later from the Chart of Accounts screen. No other column, table, or
existing report is touched.

Revision ID: 032737d62b70
Revises: 5461ff610806
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "032737d62b70"
down_revision: str | None = "5461ff610806"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column("is_cash_equivalent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # `account` has FORCE ROW LEVEL SECURITY on `company_isolation` -- same
    # NO FORCE/FORCE bracket the company.code / partner_code precedents use
    # for a bulk cross-company backfill with no app.current_company_id set.
    op.execute("ALTER TABLE account NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        WITH RECURSIVE cash_subtree AS (
            SELECT id, company_id FROM account WHERE code = '1100' AND deleted_at IS NULL
            UNION ALL
            SELECT a.id, a.company_id
            FROM account a
            JOIN cash_subtree cs ON a.parent_id = cs.id AND a.company_id = cs.company_id
            WHERE a.deleted_at IS NULL
        )
        UPDATE account
        SET is_cash_equivalent = true
        WHERE id IN (SELECT id FROM cash_subtree)
        """
    )
    op.execute("ALTER TABLE account FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_column("account", "is_cash_equivalent")
