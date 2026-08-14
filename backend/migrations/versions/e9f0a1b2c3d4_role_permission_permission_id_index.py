"""role_permission permission_id index

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-14 00:00:00.000000

Performance fix, found live: `seed_core_data()`'s Admin-role permission
sync (`backend/src/shared/infrastructure/db/seed.py`) joins
`role_permission` to `permission` on `permission_id` to find the "Admin
marker" rows (see that file's "narrow to incomplete Admin roles first"
comment). `role_permission`'s only index is its PK, `(role_id,
permission_id)` — `permission_id` isn't the leading column, so that join
cannot use it and instead forces a full sequential scan of the whole
table. On the shared dev DB, which has accumulated tens of thousands of
test-bootstrap roles (~5.4M `role_permission` rows), that scan alone was
a meaningful chunk of the query's 10+ minute runtime. This index turns it
into an index scan restricted to just the rows for the one marker
permission.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, None] = 'd8e9f0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_role_permission_permission_id", "role_permission", ["permission_id"])


def downgrade() -> None:
    op.drop_index("ix_role_permission_permission_id", table_name="role_permission")
