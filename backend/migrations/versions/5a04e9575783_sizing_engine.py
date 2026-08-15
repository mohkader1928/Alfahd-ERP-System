"""sizing engine (adaptive erp stage 2.2)

Revision ID: 5a04e9575783
Revises: 0ed664d7cf0f
Create Date: 2026-08-16 00:10:00.000000

See docs/adaptive/04-erp-sizing-engine-spec.md. `sizing_rule_set` is
deliberately NOT tenant-scoped (a global rule catalog, same shape as the
Core's own Permission/Currency/AccountType tables). `sizing_result` is
tenant-scoped like every other company table.

This migration also seeds the literal "sizing-rules-v1" rule set as data
(docs/adaptive/04 §4.3: "every weight and threshold... must live in a
versioned configuration record, never as a magic number inside
application service code") -- deliberately hardcoded here rather than
imported from application code, so this migration stays a frozen,
self-contained historical record independent of any future refactor of
src/modules/company_profile/application/sizing_rules.py.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '5a04e9575783'
down_revision: Union[str, None] = '0ed664d7cf0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SIZING_RULES_V1 = {
    "organizational_complexity": {
        "employee_bands": [10, 30, 100],
        "branch_bands": [1, 3, 10],
        "cost_center_bonus": 15,
    },
    "transaction_volume": {
        "sales_order_bands": [50, 200, 1000],
        "purchase_order_bands": [50, 200, 1000],
        "sku_bands": [50, 300, 2000],
    },
    "inventory_complexity": {
        "warehouse_bands": [1, 3, 10],
        "service_business_score": 10,
    },
    "financial_complexity": {
        "coa_depth_weight": 20,
        "cost_center_bonus": 20,
        "multi_currency_bonus": 30,
    },
    "tax_compliance_complexity": {
        "base_score": 20,
        "withholding_bonus": 40,
    },
    "asset_complexity": {
        "owns_assets_base": 30,
        "asset_count_bands": [5, 20, 100],
    },
    "approval_governance_complexity": {
        "low": 20,
        "medium": 55,
        "high": 90,
    },
    "security_access_complexity": {
        "user_bands": [5, 20, 100],
        "two_factor_bonus": 15,
    },
}


def upgrade() -> None:
    op.create_table(
        "sizing_rule_set",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.Text(), nullable=False, unique=True),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "sizing_result",
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
        sa.Column("rule_version", sa.Text(), nullable=False),
        sa.Column("dimension_scores", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_sizing_result_tenant_id", "sizing_result", ["tenant_id"])
    op.create_index("ix_sizing_result_company_id", "sizing_result", ["company_id"])
    op.create_index("ix_sizing_result_company_profile_id", "sizing_result", ["company_profile_id"])

    op.execute("ALTER TABLE sizing_result ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sizing_result FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON sizing_result
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )

    op.execute(
        sa.text("INSERT INTO sizing_rule_set (version, rules, is_active) VALUES (:version, CAST(:rules AS JSONB), true)")
        .bindparams(version="sizing-rules-v1", rules=json.dumps(SIZING_RULES_V1))
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON sizing_result")
    op.execute("ALTER TABLE sizing_result NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sizing_result DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_sizing_result_company_profile_id", table_name="sizing_result")
    op.drop_index("ix_sizing_result_company_id", table_name="sizing_result")
    op.drop_index("ix_sizing_result_tenant_id", table_name="sizing_result")
    op.drop_table("sizing_result")
    op.drop_table("sizing_rule_set")
