"""cost_center_id on quotation, sales_order, sales_invoice

Revision ID: b2c3d4e5f6a7
Revises: a66bf7a6649e
Create Date: 2026-08-17 00:00:00.000000

Owner request: attribute Sales revenue to a specific Cost Center, chosen
once on the Quotation and carried forward through Sales Order and Sales
Invoice into the auto-posted journal entry's revenue line — mirrors the
warehouse_id pattern added in f0a1b2c3d4e5. Nullable, not backfilled:
existing rows keep posting with no cost center exactly as before.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a66bf7a6649e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quotation", sa.Column("cost_center_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("sales_order", sa.Column("cost_center_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("sales_invoice", sa.Column("cost_center_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_invoice", "cost_center_id")
    op.drop_column("sales_order", "cost_center_id")
    op.drop_column("quotation", "cost_center_id")
