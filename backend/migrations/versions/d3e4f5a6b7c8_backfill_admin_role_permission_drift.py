"""backfill admin role permission drift

Revision ID: d3e4f5a6b7c8
Revises: c1d2e3f4a5b6
Create Date: 2026-08-07 00:00:00.000000

Data migration only — no schema changes.

Found live while building the Users Management screen (Bundle 2): the
Admin-role "keep in sync with new permissions" mechanism in
`seed_core_data()` selected from the `role` table directly, which carries
FORCE ROW LEVEL SECURITY keyed on company context — a context that does
not exist at API startup. The sync silently matched zero rows every time
it ran, for every DB user (including `erp_app`), since it was introduced —
not an error, just a permanent no-op. `seed_core_data()` is fixed
separately to identify Admin roles indirectly (via `role_permission`/
`permission`, which carry no RLS) instead of querying `role`. This
migration is the one-time repair for whatever drift already accumulated:
every Admin role — identified the same indirect way, by already holding
`reporting.dashboard.view` — gets every catalog permission it's missing
(confirmed live: `role.manage` was the specific gap found; this closes
that gap and any other permission added since Admin roles started
existing that never actually made it there).
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    # Not reversible in general (would strip permissions from roles that may
    # have since had them granted through normal, legitimate use of Settings
    # -> Security) — matches the same stance as c1d2e3f4a5b6's narrower
    # downgrade not attempting to distinguish "granted by this migration"
    # from "granted afterward by a real admin action".
    pass
