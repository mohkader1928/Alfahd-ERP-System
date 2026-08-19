"""Fixed asset operational status + category depreciation defaults

Standard SME ERP -- Fixed Assets Asset Master + Controlled Depreciation
phase. Owner-approved design decisions (2026-08-19):

1. `fixed_asset.status` -- an explicit OPERATIONAL status (active/idle/
   under_maintenance), separate from the existing derived
   disposed/active state (`disposed_at IS NULL`, unchanged). Additive,
   NOT NULL with a constant server_default of 'active' -- Postgres
   applies a constant DEFAULT to existing rows without a table rewrite
   (PG11+), so all 1338 existing assets become 'active' with no explicit
   backfill UPDATE needed and no RLS bracketing required (no per-row
   computation, no cross-company query). Sets no asset to 'disposed' --
   that remains solely `disposed_at`'s job, unchanged.

2. `fixed_asset_category` gains four OPTIONAL default-policy columns
   (default useful life + the three GL accounts) a new asset's create
   form can prefill from when a category is picked -- still fully
   editable per-asset, per the Owner's explicit choice. Nullable, no
   backfill: 1127/1338 (84%) of existing assets have no category at
   all, so there is nothing safe to infer a default FROM for most of
   them -- left NULL rather than invented.

No existing column, table, or asset row is modified beyond the new
`status` column's constant default. No data is deleted or recreated.

Revision ID: e4add2e2d6c4
Revises: 032737d62b70
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4add2e2d6c4"
down_revision: str | None = "032737d62b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fixed_asset",
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
    )
    op.create_check_constraint(
        "ck_fixed_asset_status",
        "fixed_asset",
        "status IN ('active', 'idle', 'under_maintenance')",
    )

    op.add_column(
        "fixed_asset_category",
        sa.Column("default_useful_life_months", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "fixed_asset_category",
        sa.Column(
            "default_fixed_asset_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("account.id"), nullable=True
        ),
    )
    op.add_column(
        "fixed_asset_category",
        sa.Column(
            "default_accumulated_depreciation_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "fixed_asset_category",
        sa.Column(
            "default_depreciation_expense_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("fixed_asset_category", "default_depreciation_expense_account_id")
    op.drop_column("fixed_asset_category", "default_accumulated_depreciation_account_id")
    op.drop_column("fixed_asset_category", "default_fixed_asset_account_id")
    op.drop_column("fixed_asset_category", "default_useful_life_months")
    op.drop_constraint("ck_fixed_asset_status", "fixed_asset", type_="check")
    op.drop_column("fixed_asset", "status")
