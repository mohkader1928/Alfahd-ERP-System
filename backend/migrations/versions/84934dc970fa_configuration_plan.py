"""configuration plan (adaptive erp stage 2.4 v1)

Revision ID: 84934dc970fa
Revises: 23451d64f3d3
Create Date: 2026-08-17 00:20:00.000000

Stage 2.4 Design & Safety Review. `configuration_plan` is one row per
attempt to apply a specific approved `erp_blueprint` version to a company
-- `UniqueConstraint(company_id, blueprint_id)` is the first of several
duplicate-application guards (see ConfigurationEngineService). Both tables
are tenant-scoped with the same RLS `company_isolation` policy pattern as
every table added since Phase 16A -- no new isolation mechanism.

No data seeding in this migration -- unlike sizing_rule_set, Configuration
Plans are always created per-company on demand, never pre-populated.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '84934dc970fa'
down_revision: str | None = '23451d64f3d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "configuration_plan",
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
        sa.Column("blueprint_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("erp_blueprint.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('draft','validated','applied','failed')", name="ck_configuration_plan_status"),
        sa.UniqueConstraint("company_id", "blueprint_id", name="ux_configuration_plan_company_blueprint"),
    )
    op.create_index("ix_configuration_plan_tenant_id", "configuration_plan", ["tenant_id"])
    op.create_index("ix_configuration_plan_company_id", "configuration_plan", ["company_id"])
    op.create_index("ix_configuration_plan_blueprint_id", "configuration_plan", ["blueprint_id"])

    op.execute("ALTER TABLE configuration_plan ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE configuration_plan FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON configuration_plan
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )

    op.create_table(
        "configuration_plan_item",
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
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("configuration_plan.id"), nullable=False),
        sa.Column("decision_key", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','skipped_already_applied','applied','failed')",
            name="ck_configuration_plan_item_status",
        ),
    )
    op.create_index("ix_configuration_plan_item_tenant_id", "configuration_plan_item", ["tenant_id"])
    op.create_index("ix_configuration_plan_item_company_id", "configuration_plan_item", ["company_id"])
    op.create_index("ix_configuration_plan_item_plan_id", "configuration_plan_item", ["plan_id"])

    op.execute("ALTER TABLE configuration_plan_item ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE configuration_plan_item FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON configuration_plan_item
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON configuration_plan_item")
    op.execute("ALTER TABLE configuration_plan_item NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE configuration_plan_item DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_configuration_plan_item_plan_id", table_name="configuration_plan_item")
    op.drop_index("ix_configuration_plan_item_company_id", table_name="configuration_plan_item")
    op.drop_index("ix_configuration_plan_item_tenant_id", table_name="configuration_plan_item")
    op.drop_table("configuration_plan_item")

    op.execute("DROP POLICY IF EXISTS company_isolation ON configuration_plan")
    op.execute("ALTER TABLE configuration_plan NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE configuration_plan DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_configuration_plan_blueprint_id", table_name="configuration_plan")
    op.drop_index("ix_configuration_plan_company_id", table_name="configuration_plan")
    op.drop_index("ix_configuration_plan_tenant_id", table_name="configuration_plan")
    op.drop_table("configuration_plan")
