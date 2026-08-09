"""fixed assets module

Revision ID: a4b5c6d7e8f9
Revises: f2a3b4c5d6e7
Create Date: 2026-08-09 00:00:00.000004

P0-5 (3-Day Brief): a Fixed Assets register integrated with the GL.
`fixed_asset` is the register itself (one row per asset, pointing at the
three GL accounts it posts to — asset, accumulated depreciation,
depreciation expense — chosen by the user from the existing Chart of
Accounts rather than a fixed/hardcoded set, matching how flexible the
CoA itself already is post-P0-4). `fixed_asset_depreciation_entry` is
one row per posted monthly depreciation run per asset, UNIQUE on
(fixed_asset_id, period_month) so the same asset can never be
depreciated twice for the same month even if "Run Depreciation" is
clicked twice — the same idempotency discipline every other document
type in this codebase already has via its own number/period uniqueness.
Accumulated depreciation and disposal status are deliberately NOT
columns on `fixed_asset` -- both are derived on read (SUM of posted
depreciation entries; disposed_at IS NOT NULL) to avoid the class of
stored-state-drift bug Phase 16B/M1b already exist to close.

Also seeds the missing Fixed Assets / Accumulated Depreciation /
Depreciation Expense / Gain-Loss-on-Disposal accounts into every
EXISTING company's Chart of Accounts (new companies get them from
DEFAULT_SAUDI_COA going forward) -- same "backfill from the data
itself" approach f2a3b4c5d6e7 used for is_group, so a company that
was onboarded before this module shipped doesn't have to hand-create
these before the Fixed Assets screen is usable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = ["fixed_asset", "fixed_asset_depreciation_entry"]


def upgrade() -> None:
    op.create_table(
        "fixed_asset",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_ar", sa.Text(), nullable=True),
        sa.Column("fixed_asset_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("accumulated_depreciation_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("depreciation_expense_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column("cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("salvage_value", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("useful_life_months", sa.SmallInteger(), nullable=False),
        sa.Column("acquisition_journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("disposed_at", sa.Date(), nullable=True),
        sa.Column("disposal_proceeds", sa.Numeric(18, 4), nullable=True),
        sa.Column("disposal_journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("cost > 0", name="ck_fixed_asset_cost_positive"),
        sa.CheckConstraint("salvage_value >= 0", name="ck_fixed_asset_salvage_non_negative"),
        sa.CheckConstraint("salvage_value < cost", name="ck_fixed_asset_salvage_below_cost"),
        sa.CheckConstraint("useful_life_months > 0", name="ck_fixed_asset_useful_life_positive"),
        sa.ForeignKeyConstraint(["fixed_asset_account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["accumulated_depreciation_account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["depreciation_expense_account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["acquisition_journal_entry_id"], ["journal_entry.id"]),
        sa.ForeignKeyConstraint(["disposal_journal_entry_id"], ["journal_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "asset_code", name="ux_fixed_asset_code"),
    )
    op.create_index(op.f("ix_fixed_asset_company_id"), "fixed_asset", ["company_id"], unique=False)

    op.create_table(
        "fixed_asset_depreciation_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fixed_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_fixed_asset_depreciation_amount_positive"),
        sa.ForeignKeyConstraint(["fixed_asset_id"], ["fixed_asset.id"]),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fixed_asset_id", "period_month", name="ux_fixed_asset_depreciation_period"),
    )
    op.create_index(
        op.f("ix_fixed_asset_depreciation_entry_company_id"),
        "fixed_asset_depreciation_entry", ["company_id"], unique=False,
    )
    op.create_index(
        op.f("ix_fixed_asset_depreciation_entry_fixed_asset_id"),
        "fixed_asset_depreciation_entry", ["fixed_asset_id"], unique=False,
    )

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY company_isolation ON {table}
            USING (company_id = current_setting('app.current_company_id', true)::uuid)
            WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
            """
        )

    op.execute("ALTER TABLE account NO FORCE ROW LEVEL SECURITY")

    # "1400 Fixed Assets" — new level-2 group under each company's own
    # existing "1000 Assets" (skipped for a company that no longer has a
    # 1000 row, e.g. one whose CoA was hand-rebuilt from scratch).
    op.execute(
        """
        INSERT INTO account (id, company_id, code, name, name_ar, account_type_id, parent_id, level, is_group)
        SELECT gen_random_uuid(), parent.company_id, '1400', 'Fixed Assets', 'الأصول الثابتة',
               (SELECT id FROM account_type WHERE code = 'asset'), parent.id, parent.level + 1, true
        FROM account parent
        WHERE parent.code = '1000' AND parent.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM account existing
              WHERE existing.company_id = parent.company_id AND existing.code = '1400'
          )
        """
    )
    # "1410 Property, Plant & Equipment" and "1490 Accumulated
    # Depreciation" — leaf accounts under the 1400 group just inserted.
    op.execute(
        """
        INSERT INTO account (id, company_id, code, name, name_ar, account_type_id, parent_id, level, is_group)
        SELECT gen_random_uuid(), parent.company_id, '1410', 'Property, Plant & Equipment', 'الممتلكات والمعدات',
               (SELECT id FROM account_type WHERE code = 'asset'), parent.id, parent.level + 1, false
        FROM account parent
        WHERE parent.code = '1400' AND parent.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM account existing
              WHERE existing.company_id = parent.company_id AND existing.code = '1410'
          )
        """
    )
    op.execute(
        """
        INSERT INTO account (id, company_id, code, name, name_ar, account_type_id, parent_id, level, is_group)
        SELECT gen_random_uuid(), parent.company_id, '1490', 'Accumulated Depreciation', 'مجمع الإهلاك',
               (SELECT id FROM account_type WHERE code = 'asset'), parent.id, parent.level + 1, false
        FROM account parent
        WHERE parent.code = '1400' AND parent.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM account existing
              WHERE existing.company_id = parent.company_id AND existing.code = '1490'
          )
        """
    )
    # "5950 Depreciation Expense" under each company's existing "5000
    # Expenses"; "4900 Gain on Disposal of Fixed Assets" under "4000
    # Revenue"; "5900 Loss on Disposal of Fixed Assets" under "5000
    # Expenses" -- skipped (NOT EXISTS) for any company that already has
    # its own account at that code (confirmed live: some companies already
    # have a hand-added 5900 of their own).
    op.execute(
        """
        INSERT INTO account (id, company_id, code, name, name_ar, account_type_id, parent_id, level, is_group)
        SELECT gen_random_uuid(), parent.company_id, '5950', 'Depreciation Expense', 'مصروف الإهلاك',
               (SELECT id FROM account_type WHERE code = 'expense'), parent.id, parent.level + 1, false
        FROM account parent
        WHERE parent.code = '5000' AND parent.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM account existing
              WHERE existing.company_id = parent.company_id AND existing.code = '5950'
          )
        """
    )
    op.execute(
        """
        INSERT INTO account (id, company_id, code, name, name_ar, account_type_id, parent_id, level, is_group)
        SELECT gen_random_uuid(), parent.company_id, '4900', 'Gain on Disposal of Fixed Assets', 'أرباح استبعاد الأصول الثابتة',
               (SELECT id FROM account_type WHERE code = 'revenue'), parent.id, parent.level + 1, false
        FROM account parent
        WHERE parent.code = '4000' AND parent.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM account existing
              WHERE existing.company_id = parent.company_id AND existing.code = '4900'
          )
        """
    )
    op.execute(
        """
        INSERT INTO account (id, company_id, code, name, name_ar, account_type_id, parent_id, level, is_group)
        SELECT gen_random_uuid(), parent.company_id, '5900', 'Loss on Disposal of Fixed Assets', 'خسائر استبعاد الأصول الثابتة',
               (SELECT id FROM account_type WHERE code = 'expense'), parent.id, parent.level + 1, false
        FROM account parent
        WHERE parent.code = '5000' AND parent.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM account existing
              WHERE existing.company_id = parent.company_id AND existing.code = '5900'
          )
        """
    )

    op.execute("ALTER TABLE account FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE account NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "DELETE FROM account WHERE code IN ('1410', '1490', '5950', '4900', '5900', '1400') "
        "AND deleted_at IS NULL"
    )
    op.execute("ALTER TABLE account FORCE ROW LEVEL SECURITY")

    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("fixed_asset_depreciation_entry")
    op.drop_table("fixed_asset")
