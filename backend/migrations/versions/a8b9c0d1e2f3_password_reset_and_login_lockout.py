"""password reset tokens + login lockout columns on app_user

Revision ID: a8b9c0d1e2f3
Revises: f0a1b2c3d4e5
Create Date: 2026-08-14 00:00:00.000000

Owner-approved Phase-One closure (P0-A, P0-B): the audit found neither a
password-reset path nor a login-lockout mechanism anywhere in the
codebase. `password_reset_token` deliberately has no `company_id`/RLS —
it is looked up exclusively by an unguessable token hash before any
company context can exist (the exact same "runs before auth" shape as
`app_user`'s own login-lookup RLS escape hatch), so there is no
cross-tenant data to isolate. Lockout state lives directly on `app_user`
since it's a property of the account, not a separate ledger.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_reset_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="ux_password_reset_token_hash"),
    )
    op.create_index("ix_password_reset_token_user_id", "password_reset_token", ["user_id"])

    op.add_column(
        "app_user", sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    op.add_column("app_user", sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_user", "locked_until")
    op.drop_column("app_user", "failed_login_count")
    op.drop_index("ix_password_reset_token_user_id", table_name="password_reset_token")
    op.drop_table("password_reset_token")
