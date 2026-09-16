"""Accounting Settings — configurable inventory adjustment account (INV-002)

Revision ID: 687d818314fd
Revises: c3d8e91a4f27
Create Date: 2026-09-16 00:00:00.000000

INV-002 (production incident): Cycle Count approval hardcoded account code
"5200" ("Operating Expenses") as its shortage/surplus adjustment account.
This broke the moment any company added a sub-account under it -- an
ordinary, encouraged bookkeeping action (e.g. Salaries, Rent, Commission)
that auto-promotes the parent to a group account, which
JournalEntryService.create_draft_entry correctly refuses to post to.
Confirmed live in production for "Ehab Abdelrahman Testing Co." (the same
company as BASELINE-DRIFT-001) but latent in every company from day one,
since DEFAULT_SAUDI_COA never seeds a child of 5200 -- any company that
grows its Chart of Accounts past the bare seed template and then runs a
Cycle Count adjustment will eventually hit this.

Adds `accounting_settings`: one row per company, holding
`inventory_adjustment_account_id` (nullable FK to `account.id`). Per
Owner's explicit accounting-policy decision, ONE account is used for both
shortage and surplus -- debit/credit polarity distinguishes the two, no
separate accounts. Mirrors the Fixed Assets category-defaults FK-to-
account pattern (see e3f4a5b6c7d8_fixed_asset_category.py /
e4add2e2d6c4_fixed_asset_status_and_category_defaults.py) and the
company_isolation RLS shape used by every other company-scoped table
(most recently commission_transaction, c3d8e91a4f27).

Purely additive, no data backfill: the table starts completely empty for
EVERY company -- existing and newly bootstrapped alike. Per Owner's
explicit design correction, Option 2 was chosen specifically so each
company makes its OWN explicit choice of adjustment account; automatically
defaulting new companies to their freshly-seeded "5200" (an earlier
iteration of this change did exactly that) would have just replaced one
implicit-5200 dependency with another. Every company, new or existing,
stays unconfigured (NULL / no row) until an administrator explicitly
selects a real account via PATCH /api/v1/accounting/settings -- Cycle
Count approval handles "not configured" as a controlled 4xx business
error (AccountingSettingsService.resolve_inventory_adjustment_account),
never a crash and never a silent guess.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '687d818314fd'
down_revision: str | None = 'c3d8e91a4f27'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounting_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "inventory_adjustment_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("company_id", name="ux_accounting_settings_company"),
    )
    op.create_index(
        "ix_accounting_settings_company_id", "accounting_settings", ["company_id"], unique=False
    )

    op.execute("ALTER TABLE accounting_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE accounting_settings FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON accounting_settings
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON accounting_settings")
    op.execute("ALTER TABLE accounting_settings NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE accounting_settings DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_accounting_settings_company_id", table_name="accounting_settings")
    op.drop_table("accounting_settings")
