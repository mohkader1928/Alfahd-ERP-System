"""row level security tenant isolation

Revision ID: 42bc09c34924
Revises: 42f822ff912d
Create Date: 2026-07-31 18:53:17.095380
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '42bc09c34924'
down_revision: Union[str, None] = '42f822ff912d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RLS_TABLES = ["company", "branch", "app_user", "audit_log", "activity_log"]


def upgrade() -> None:
    # Phase 7 §1.4: belt-and-suspenders tenant isolation at the DB layer.
    # FORCE ROW LEVEL SECURITY is required because Postgres exempts the
    # table owner from RLS by default — and the app connects as the owning
    # role (`erp`) that ran the migrations, so without FORCE the policy
    # below would silently do nothing.
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            """
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
