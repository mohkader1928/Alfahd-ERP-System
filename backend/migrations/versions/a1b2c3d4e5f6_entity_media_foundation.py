"""entity_media_foundation

Revision ID: a1b2c3d4e5f6
Revises: 5955ce0f8dd6
Create Date: 2026-08-03 00:00:00.000000

UI/UX Evolution milestone — Entity Media Foundation. Adds a single
nullable path column to each entity that can carry an image: `logo_path`
on `company`, `image_path` on `partner` (covers both customer and
vendor), `image_path` on `product`. Purely additive, no backfill needed —
mirrors the exact pattern `5955ce0f8dd6` already used for `due_date`.
Stores a relative path only (e.g. "company/<uuid>/<uuid>.png"), never a
full URL — see backend/src/shared/media/storage.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5955ce0f8dd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("company", sa.Column("logo_path", sa.Text(), nullable=True))
    op.add_column("partner", sa.Column("image_path", sa.Text(), nullable=True))
    op.add_column("product", sa.Column("image_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("product", "image_path")
    op.drop_column("partner", "image_path")
    op.drop_column("company", "logo_path")
