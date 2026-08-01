"""rls for inventory tables

Revision ID: c7d1f40b5718
Revises: 5795e21946f2
Create Date: 2026-07-31 20:21:36.099156
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d1f40b5718'
down_revision: Union[str, None] = '5795e21946f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = ["warehouse", "stock_move", "stock_quant", "stock_layer", "cycle_count"]


def upgrade() -> None:
    # Phase 7 §1.4, extended for M3. `location` and `cycle_count_line` have
    # no company_id column of their own (detail/join tables reached only
    # through their parent), matching the journal_entry_line precedent.
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
