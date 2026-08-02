"""phase17c_step3a_user_company_access_login_lookup_policy

Revision ID: 0fc571b91522
Revises: f7004fe055a4
Create Date: 2026-08-01 21:32:17.350560

Phase 17C-RLS Step 3A (companion to f7004fe055a4): `AuthenticationService.
issue_tokens()` calls `UserRepository.list_authorized_companies()` right
after a successful login/2FA verify, to list which companies the new JWT
should authorize — before any company context can exist, for exactly the
same reason app_user's email lookup can't have tenant context yet.
`user_company_access` carries `company_isolation` RLS (Phase 16A,
8957d3c39d54), so under real RLS enforcement that query returned zero rows
every time, silently issuing tokens with an empty authorized-companies
list. Same fix, same gate: an additive, SELECT-only policy reusing the
identical `app.login_lookup` transaction-local flag — no new mechanism,
and the existing `company_isolation` policy (governing this table's SELECT
as well as all of its INSERT/UPDATE/DELETE) is untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0fc571b91522'
down_revision: Union[str, None] = 'f7004fe055a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY user_company_access_login_lookup ON user_company_access
        FOR SELECT
        USING (current_setting('app.login_lookup', true) = 'true')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_company_access_login_lookup ON user_company_access")
