"""purchase order line short-close

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-09 00:00:00.000000

3-Day Sellable Product Brief, P0-1: real partial receipt already worked
at the data layer (purchase_order_line.qty_received accumulates across
multiple goods receipts, over-receipt already blocked by
record_receipt) — what was missing was a way to deliberately stop
short of the ordered qty ("short close") instead of leaving the PO
open forever, and a PO status that reflects that decision distinctly
from "fully received as ordered".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "purchase_order_line",
        sa.Column("short_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_constraint("ck_purchase_order_status", "purchase_order", type_="check")
    op.create_check_constraint(
        "ck_purchase_order_status",
        "purchase_order",
        "status IN ('draft', 'pending_approval', 'confirmed', 'done', 'closed', 'cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_purchase_order_status", "purchase_order", type_="check")
    op.create_check_constraint(
        "ck_purchase_order_status",
        "purchase_order",
        "status IN ('draft', 'pending_approval', 'confirmed', 'done', 'cancelled')",
    )
    op.drop_column("purchase_order_line", "short_closed")
