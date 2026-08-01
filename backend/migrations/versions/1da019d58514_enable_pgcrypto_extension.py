"""enable pgcrypto extension

Revision ID: 1da019d58514
Revises: 
Create Date: 2026-07-31 18:52:24.180729
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1da019d58514'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
