"""rls for partner product sales tables

Revision ID: f81e8530ddbd
Revises: 85e635298389
Create Date: 2026-07-31 19:36:24.567475
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f81e8530ddbd'
down_revision: Union[str, None] = '85e635298389'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = ["partner", "product", "product_category", "quotation", "sales_order", "sales_invoice"]


def upgrade() -> None:
    # Phase 7 §1.4, extended for M2. Partner/Product carry both tenant_id and
    # company_id (Phase 6 §2), but company_id is the scope every repository
    # actually filters by, so RLS here is keyed the same way as
    # Accounting/Sales rather than tenant_id, for consistency with the rest
    # of this company_id-scoped tier.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY company_isolation ON {table}
            USING (company_id = current_setting('app.current_company_id', true)::uuid)
            WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
            """
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
