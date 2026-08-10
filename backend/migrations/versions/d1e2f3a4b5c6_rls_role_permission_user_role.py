"""RLS for role_permission and user_role (join-table isolation)

Revision ID: d1e2f3a4b5c6
Revises: a4b5c6d7e8f9
Create Date: 2026-08-10 00:00:00.000000

P0-6 RBAC audit finding: `role_permission` and `user_role` are pure join
tables (composite PK only, no `company_id` column of their own) and had
`relrowsecurity=false` — no RLS at all, unlike `role` and
`user_company_access` which were hardened in Phase 16A (8957d3c39d54).
Isolation for these two tables depended entirely on application code
always filtering by a company-scoped role_id, which happens to hold today
but is not enforced by the database itself.

Neither table can carry a direct `company_id` column the way Phase 16A's
line tables do (a join table has no natural "add and backfill a column"
shape — both rows are keyed entirely by the parent FKs). Instead, the
policy is an EXISTS subquery against `role.company_id`, reached through
`role_id` on both tables — `role` itself is already RLS-protected, but a
subquery inside another table's own RLS policy runs with that policy
context, not through `role`'s policy, so this must be stated explicitly
here rather than relied upon transitively.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, role_id_column)
JOIN_TABLES = [
    ("role_permission", "role_id"),
    ("user_role", "role_id"),
]


def upgrade() -> None:
    for table, role_col in JOIN_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY company_isolation ON {table}
            USING (EXISTS (
                SELECT 1 FROM role
                WHERE role.id = {table}.{role_col}
                AND role.company_id = current_setting('app.current_company_id', true)::uuid
            ))
            WITH CHECK (EXISTS (
                SELECT 1 FROM role
                WHERE role.id = {table}.{role_col}
                AND role.company_id = current_setting('app.current_company_id', true)::uuid
            ))
            """
        )


def downgrade() -> None:
    for table, _ in JOIN_TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
