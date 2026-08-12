"""backfill admin role permission drift (2)

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-08-12 00:00:00.000000

Data migration only — no schema changes.

The exact same class of bug `d3e4f5a6b7c8` already fixed once, recurring
on a different table. Found live: `fixed_assets.category.manage`
(added this session) never reached any existing company's Admin role,
even after many API restarts — the Categories screen had no "New
Category" button and looked broken for a fully-permissioned demo user.

Root cause: `seed_core_data()`'s Admin-role sync (in
`src/shared/infrastructure/db/seed.py`) runs as `erp_app`, which does
NOT own `role_permission` — ownership sits with `erp_migrate` (see
`a4b5c6d7e8f9`'s bootstrap-role reassignment). `role_permission` has
carried `FORCE ROW LEVEL SECURITY` since a later change added RLS to it
and `user_role` (P0-6). Since `erp_app` isn't the table owner, RLS
applies to it regardless of FORCE, and the sync's SELECT against
`role_permission` runs with no `app.current_company_id` GUC set (there
is no per-request company context at API startup) — so the
company-scoped `USING`/`WITH CHECK` policy silently matches zero rows,
every time, for every company. The sync has been a permanent no-op
since RLS landed on `role_permission`, not just for this one permission.

This migration is the one-time repair, using the exact same detection
and INSERT as `d3e4f5a6b7c8`: any role already holding
`reporting.dashboard.view` (the same "this is an Admin role" marker)
gets every catalog permission it's missing. `role_permission` carries
FORCE ROW LEVEL SECURITY, which applies RLS even to the owning role
(`erp_migrate`) — so the same `NO FORCE`/`FORCE ROW LEVEL SECURITY`
bracketing `f4a5b6c7d8e9` used for `partner` is required here too for
this cross-company write.

The runtime sync itself is a separate, deeper fix (making it operate
per-company, since `erp_app` structurally cannot run a single
cross-company query against a FORCE-RLS table it doesn't own) — out of
scope for this one-time repair, tracked separately.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE role_permission NO FORCE ROW LEVEL SECURITY")
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT DISTINCT admin_rp.role_id, p_missing.id
        FROM role_permission admin_rp
        JOIN permission p_marker ON p_marker.id = admin_rp.permission_id
                                  AND p_marker.code = 'reporting.dashboard.view'
        CROSS JOIN permission p_missing
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permission rp2
            WHERE rp2.role_id = admin_rp.role_id AND rp2.permission_id = p_missing.id
        )
    """)
    op.execute("ALTER TABLE role_permission FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Not reversible in general — matches d3e4f5a6b7c8's same stance (would
    # strip permissions from roles that may have since had them granted
    # through normal, legitimate use of Settings -> Security).
    pass
