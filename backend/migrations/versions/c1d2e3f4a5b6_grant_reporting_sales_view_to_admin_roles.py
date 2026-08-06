"""grant reporting.sales.view to existing Admin roles

Revision ID: c1d2e3f4a5b6
Revises: b2c4e6f8a1d3
Create Date: 2026-08-05 00:00:00.000000

Data migration only — no schema changes.

Problem: The `role` table has FORCE ROW LEVEL SECURITY, so neither erp_app
nor erp_migrate can query it without a company context GUC — which does not
exist at migration time.  We therefore identify Admin roles indirectly:
any role that already holds `reporting.dashboard.view` was created with the
full PERMISSION_CATALOG (i.e. it is an Admin role) and must also receive the
new `reporting.sales.view` permission.

Both `permission` and `role_permission` have no RLS, so this query works
unconditionally regardless of the active DB user.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b2c4e6f8a1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Grant `reporting.sales.view` to every role that already holds
    # `reporting.dashboard.view`.  Only Admin roles have that permission,
    # so this precisely targets the right set without touching `role` table.
    # ON CONFLICT DO NOTHING makes the statement idempotent.
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT rp.role_id, p_new.id
        FROM role_permission rp
        JOIN permission p_ref  ON p_ref.id  = rp.permission_id
                               AND p_ref.code = 'reporting.dashboard.view'
        JOIN permission p_new  ON p_new.code = 'reporting.sales.view'
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permission rp2
            WHERE rp2.role_id      = rp.role_id
              AND rp2.permission_id = p_new.id
        )
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Remove reporting.sales.view from any role that holds
    # reporting.dashboard.view (reverses the upgrade exactly).
    op.execute("""
        DELETE FROM role_permission
        WHERE permission_id = (SELECT id FROM permission WHERE code = 'reporting.sales.view')
          AND role_id IN (
              SELECT rp.role_id
              FROM role_permission rp
              JOIN permission p ON p.id = rp.permission_id
              WHERE p.code = 'reporting.dashboard.view'
          )
    """)
