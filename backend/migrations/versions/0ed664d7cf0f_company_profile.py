"""company profile (adaptive erp stage 2.1)

Revision ID: 0ed664d7cf0f
Revises: a8b9c0d1e2f3
Create Date: 2026-08-16 00:00:00.000000

See docs/adaptive/03-customer-profile-spec.md and
docs/adaptive/06-configuration-engine-architecture.md §6.3/§6.7 — a new,
purely additive table, separate from `company` (never ALTERs an existing
table), 1:1 with company.id via a unique constraint. Existing companies
get no row here by default (docs/adaptive/06 §6.7 / docs/adaptive/12
Principle 7: absence of a profile means "behaves exactly as v1.0.0 does
today").
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0ed664d7cf0f'
down_revision: Union[str, None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("legal_form", sa.Text(), nullable=True),
        sa.Column("employee_count", sa.Integer(), nullable=True),
        sa.Column("branch_count", sa.Integer(), nullable=True),
        sa.Column("cost_center_tracking_needed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_service_business", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("warehouse_count", sa.Integer(), nullable=True),
        sa.Column("monthly_sales_order_volume", sa.Integer(), nullable=True),
        sa.Column("monthly_purchase_order_volume", sa.Integer(), nullable=True),
        sa.Column("sku_count_estimate", sa.Integer(), nullable=True),
        sa.Column("coa_depth_preference", sa.SmallInteger(), nullable=True),
        sa.Column("multi_currency_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("withholding_tax_needed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("owns_fixed_assets", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fixed_asset_count_estimate", sa.Integer(), nullable=True),
        sa.Column("approval_rigor_preference", sa.Text(), nullable=False, server_default=sa.text("'low'")),
        sa.Column("desired_user_count", sa.Integer(), nullable=True),
        sa.Column("two_factor_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("growth_notes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("company_id", name="ux_company_profile_company_id"),
        sa.CheckConstraint(
            "approval_rigor_preference IN ('low','medium','high')",
            name="ck_company_profile_approval_rigor",
        ),
        sa.CheckConstraint(
            "coa_depth_preference IS NULL OR (coa_depth_preference BETWEEN 1 AND 4)",
            name="ck_company_profile_coa_depth",
        ),
    )
    op.create_index("ix_company_profile_tenant_id", "company_profile", ["tenant_id"])
    op.create_index("ix_company_profile_company_id", "company_profile", ["company_id"])

    # Same RLS pattern as every company-scoped table since Phase 16A
    # (docs/adaptive/06 §6.6 — "no new isolation mechanism").
    op.execute("ALTER TABLE company_profile ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE company_profile FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON company_profile
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON company_profile")
    op.execute("ALTER TABLE company_profile NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE company_profile DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_company_profile_company_id", table_name="company_profile")
    op.drop_index("ix_company_profile_tenant_id", table_name="company_profile")
    op.drop_table("company_profile")
