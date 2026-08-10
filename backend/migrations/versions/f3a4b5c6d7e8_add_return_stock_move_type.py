"""Add 'return' to stock_move.move_type (Sales/Purchase Returns)

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-08-11 00:00:00.000000

Product Owner request: a Sales Credit Note / Purchase Debit Note only
ever reversed the financial side (AR/AP, revenue, VAT) — goods were
never actually moved back into or out of the warehouse. Widens the
`ck_stock_move_type` CHECK constraint to allow a distinct 'return' move
type, so a restocked return is visibly distinguishable from an ordinary
receipt/delivery in the product cardex and stock-moves list, rather than
overloading an existing move_type with a different meaning.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TYPES = "('receipt', 'delivery', 'transfer', 'adjustment')"
NEW_TYPES = "('receipt', 'delivery', 'transfer', 'adjustment', 'return')"


def upgrade() -> None:
    op.drop_constraint("ck_stock_move_type", "stock_move", type_="check")
    op.create_check_constraint("ck_stock_move_type", "stock_move", f"move_type IN {NEW_TYPES}")


def downgrade() -> None:
    op.drop_constraint("ck_stock_move_type", "stock_move", type_="check")
    op.create_check_constraint("ck_stock_move_type", "stock_move", f"move_type IN {OLD_TYPES}")
