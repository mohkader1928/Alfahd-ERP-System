"""Commercial Performance Stage 2A — sales representative master entity

Revision ID: 1954ea58d959
Revises: 625530a27ae2
Create Date: 2026-08-30 00:00:00.000000

Purely additive, approved Stage 2A scope only:

1. New `sales_representative` table — a minimal, company-scoped commercial
   master-data entity (id, company_id, name, code, is_active,
   commission_rate, created_at). NOT an HR/employee record by explicit
   Owner decision (no department/manager/hire_date/salary), and
   deliberately separate from both `partner` and `app_user`. RLS enabled
   with the exact same `company_isolation` policy shape already used by
   every other company-scoped table in this schema (see e.g.
   `company_address`, migration fa62b281bdfc).

2. `partner.default_sales_rep_id` — a new nullable FK to
   `sales_representative.id`. Master-data only: this stage does NOT add
   any snapshot field to Quotation/SalesOrder/SalesInvoice/Payment (that
   is explicitly deferred to a later, separate stage per Owner decision).

No backfill: every existing partner keeps `default_sales_rep_id = NULL`,
and the new table starts empty, so all existing records keep working
unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '1954ea58d959'
down_revision: Union[str, None] = '625530a27ae2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. sales_representative: new company-scoped master table ---
    op.create_table(
        "sales_representative",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("commission_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("company_id", "code", name="ux_sales_representative_code"),
    )
    op.create_index(
        "ix_sales_representative_company_id", "sales_representative", ["company_id"], unique=False
    )

    op.execute("ALTER TABLE sales_representative ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales_representative FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON sales_representative
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )

    # --- 2. partner.default_sales_rep_id: new nullable FK, master data only ---
    op.add_column(
        "partner",
        sa.Column(
            "default_sales_rep_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_representative.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("partner", "default_sales_rep_id")

    op.execute("DROP POLICY IF EXISTS company_isolation ON sales_representative")
    op.execute("ALTER TABLE sales_representative NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales_representative DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_sales_representative_company_id", table_name="sales_representative")
    op.drop_table("sales_representative")
