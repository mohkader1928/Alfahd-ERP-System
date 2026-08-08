"""purchase order partially_received status

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-09 00:00:00.000001

Owner feedback on the short-close bundle: the PO's status should
honestly reflect its data at all times, not stay 'confirmed' through a
partial receipt as if nothing had happened. Also: each goods receipt
now auto-issues its own vendor bill for exactly what was received (the
Owner's explicit call — billing is no longer a separate manual step),
so a receipt is the one moment that actually determines the order's
real state (partially_received / done / stays confirmed if nothing
received yet).
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_purchase_order_status", "purchase_order", type_="check")
    op.create_check_constraint(
        "ck_purchase_order_status",
        "purchase_order",
        "status IN ('draft', 'pending_approval', 'confirmed', 'partially_received', 'done', 'closed', 'cancelled')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_purchase_order_status", "purchase_order", type_="check")
    op.create_check_constraint(
        "ck_purchase_order_status",
        "purchase_order",
        "status IN ('draft', 'pending_approval', 'confirmed', 'done', 'closed', 'cancelled')",
    )
