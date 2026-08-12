"""fixed asset category

Revision ID: e3f4a5b6c7d8
Revises: c4d5e6f7a8b9
Create Date: 2026-08-12 00:00:00.000000

Owner request: split Fixed Assets into its own independent section with
asset classification, so depreciation can be run for one specific group
of assets rather than only "all assets". `fixed_asset_category` mirrors
`product_category` exactly (self-referencing tree: id, company_id, name,
parent_id) -- the same minimal shape already proven for product
classification, reused here rather than inventing a second pattern.
`fixed_asset.category_id` is nullable so every existing asset stays
valid without a backfill; uncategorized simply means "no group" for the
category-scoped depreciation run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fixed_asset_category",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["fixed_asset_category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_fixed_asset_category_company_id"), "fixed_asset_category", ["company_id"], unique=False
    )

    op.execute("ALTER TABLE fixed_asset_category ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fixed_asset_category FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON fixed_asset_category
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )

    op.add_column("fixed_asset", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_fixed_asset_category_id", "fixed_asset", "fixed_asset_category", ["category_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_fixed_asset_category_id", "fixed_asset", type_="foreignkey")
    op.drop_column("fixed_asset", "category_id")

    op.execute("DROP POLICY IF EXISTS company_isolation ON fixed_asset_category")
    op.execute("ALTER TABLE fixed_asset_category NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fixed_asset_category DISABLE ROW LEVEL SECURITY")

    op.drop_table("fixed_asset_category")
