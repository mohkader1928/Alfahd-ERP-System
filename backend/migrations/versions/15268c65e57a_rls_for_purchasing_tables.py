"""rls for purchasing tables

Revision ID: 15268c65e57a
Revises: fc93d906d5ba
Create Date: 2026-07-31 20:48:28.761268
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '15268c65e57a'
down_revision: Union[str, None] = 'fc93d906d5ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = ["purchase_order", "goods_receipt", "vendor_bill"]


def upgrade() -> None:
    # Phase 7 §1.4, extended for M4. Line/detail tables (purchase_order_line,
    # goods_receipt_line, vendor_bill_line) have no company_id of their own,
    # matching every prior module's precedent.
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
