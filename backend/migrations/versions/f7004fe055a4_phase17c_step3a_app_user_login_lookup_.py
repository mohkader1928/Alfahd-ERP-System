"""phase17c_step3a_app_user_login_lookup_policy

Revision ID: f7004fe055a4
Revises: a3f6e2c9d1b4
Create Date: 2026-08-01 21:27:22.810753

Phase 17C-RLS Step 3A: `app_user` has carried `tenant_isolation` RLS with
FORCE ROW LEVEL SECURITY since the original M0 migration
(42bc09c34924_row_level_security_tenant_isolation.py) —
`USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)`.
That was invisible for the whole project history because the API always
connected as the `erp` superuser (unconditionally bypasses RLS). Once the
runtime role became `erp_app` (no bypass), the unauthenticated login/2FA
flow's user-by-email lookup — which by definition runs before any tenant is
known — could never see a row: confirmed empirically against a fresh
`erp_app` session with no context set, `SELECT count(*) FROM app_user`
returns 0.

This adds a second, ADDITIVE, SELECT-only policy. It does not touch the
existing `tenant_isolation` policy in any way — Postgres OR's permissive
policies together per command, so ordinary authenticated SELECTs (and every
INSERT/UPDATE/DELETE, still governed solely by `tenant_isolation`, the only
policy defined for those commands) behave exactly as before. The new
policy only ever grants SELECT, and only when the transaction-local
`app.login_lookup` flag has been explicitly set to 'true' by trusted
server-side code (see `set_login_lookup()` in
`src/shared/infrastructure/db/session.py`) — never client-controllable,
never set outside the login/verify-2fa route handlers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7004fe055a4'
down_revision: Union[str, None] = 'a3f6e2c9d1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY app_user_login_lookup ON app_user
        FOR SELECT
        USING (current_setting('app.login_lookup', true) = 'true')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS app_user_login_lookup ON app_user")
