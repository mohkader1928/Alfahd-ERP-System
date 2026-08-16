"""erp blueprint (adaptive erp stage 2.3)

Revision ID: 23451d64f3d3
Revises: 5a04e9575783
Create Date: 2026-08-17 00:10:00.000000

See docs/adaptive/05-erp-blueprint-spec.md. `erp_blueprint` is tenant-scoped
like every other company table (RLS company_isolation policy, same as
sizing_result). A Blueprint never mutates business data directly -- it only
records decisions for the Configuration Engine (Stage 2.4) to apply.

This migration also updates the existing "sizing-rules-v1" sizing_rule_set
row to add a "blueprint_decisions" key holding the threshold values
generate_decisions() (application/blueprint_rules.py) reads -- kept in the
same versioned configuration record as the sizing weights, per
docs/adaptive/04 §4.3's "every weight and threshold... must live in a
versioned configuration record, never as a magic number inside application
service code," which applies equally to Blueprint decision thresholds.
"""
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '23451d64f3d3'
down_revision: str | None = '5a04e9575783'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BLUEPRINT_DECISION_THRESHOLDS = {
    "approval_threshold_amounts": {"low": 5000, "medium": 20000, "high": 100000},
    "security_high_role_threshold": 20,
    "financial_complexity_cost_center_threshold": 40,
    "organizational_complexity_branch_threshold": 40,
}


def upgrade() -> None:
    op.create_table(
        "erp_blueprint",
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
        sa.Column("company_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_profile.id"), nullable=False),
        sa.Column("sizing_result_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sizing_result.id"), nullable=False),
        sa.Column("blueprint_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("decisions", postgresql.JSONB(), nullable=False),
        sa.Column("enabled_modules", postgresql.JSONB(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("status IN ('draft','approved','superseded')", name="ck_erp_blueprint_status"),
        sa.UniqueConstraint("company_id", "blueprint_version", name="ux_erp_blueprint_company_version"),
    )
    op.create_foreign_key(
        "fk_erp_blueprint_superseded_by_id", "erp_blueprint", "erp_blueprint", ["superseded_by_id"], ["id"]
    )
    op.create_index("ix_erp_blueprint_tenant_id", "erp_blueprint", ["tenant_id"])
    op.create_index("ix_erp_blueprint_company_id", "erp_blueprint", ["company_id"])
    op.create_index("ix_erp_blueprint_company_profile_id", "erp_blueprint", ["company_profile_id"])

    op.execute("ALTER TABLE erp_blueprint ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE erp_blueprint FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON erp_blueprint
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )

    op.execute(
        sa.text(
            "UPDATE sizing_rule_set SET rules = rules || CAST(:decisions AS JSONB) WHERE version = :version"
        ).bindparams(
            version="sizing-rules-v1",
            decisions=json.dumps({"blueprint_decisions": BLUEPRINT_DECISION_THRESHOLDS}),
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE sizing_rule_set SET rules = rules - 'blueprint_decisions' WHERE version = :version").bindparams(
            version="sizing-rules-v1"
        )
    )

    op.execute("DROP POLICY IF EXISTS company_isolation ON erp_blueprint")
    op.execute("ALTER TABLE erp_blueprint NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE erp_blueprint DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_erp_blueprint_company_profile_id", table_name="erp_blueprint")
    op.drop_index("ix_erp_blueprint_company_id", table_name="erp_blueprint")
    op.drop_index("ix_erp_blueprint_tenant_id", table_name="erp_blueprint")
    op.drop_constraint("fk_erp_blueprint_superseded_by_id", "erp_blueprint", type_="foreignkey")
    op.drop_table("erp_blueprint")
