"""admin sync role_permission policy

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-08-12 00:00:00.000000

Root-cause fix for the bug `a5b6c7d8e9f0` only patched the symptom of:
`seed_core_data()`'s Admin-role permission sync (`backend/src/shared/
infrastructure/db/seed.py`) has been a silent no-op since RLS landed on
`role_permission` (P0-6) — it runs as `erp_app`, which doesn't own that
table, at API startup where no `app.current_company_id` context exists
yet, so the `company_isolation` policy blocks every row.

Same shape of problem the login flow already solved for `user_company_
access` (`f7004fe055a4`/`0fc571b91522`): `AuthenticationService.
issue_tokens()` needs to read across companies before any company
context can exist either. That fix added a second, narrow, ADDITIVE
permissive policy gated by a transaction-local flag
(`app.login_lookup`) — Postgres OR's multiple permissive policies for
the same command together, so this doesn't touch or weaken
`company_isolation` at all, it just gives one specific, narrowly-scoped
system operation another way to satisfy the policy.

This migration adds the identical shape of escape hatch to
`role_permission`, gated by a new flag `app.admin_sync`, split into a
SELECT policy (needed for the sync's own "which admin roles are
incomplete" read, and for the INSERT...SELECT's read side) and an
INSERT policy (for the actual grant) — no UPDATE/DELETE policy, since
the sync never needs those. `src/shared/infrastructure/db/session.py`
gets a matching `set_admin_sync()` helper (mirroring `set_login_lookup`)
that `seed_core_data()` calls immediately before running the sync.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b6c7d8e9f0a1'
down_revision: Union[str, None] = 'a5b6c7d8e9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY role_permission_admin_sync_read ON role_permission
        FOR SELECT
        USING (current_setting('app.admin_sync', true) = 'true')
        """
    )
    op.execute(
        """
        CREATE POLICY role_permission_admin_sync_write ON role_permission
        FOR INSERT
        WITH CHECK (current_setting('app.admin_sync', true) = 'true')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS role_permission_admin_sync_write ON role_permission")
    op.execute("DROP POLICY IF EXISTS role_permission_admin_sync_read ON role_permission")
