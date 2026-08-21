"""inventory valuation variance account

Revision ID: b4c5d6e7f8a9
Revises: f7a8b9c0d1e2
Create Date: 2026-08-21 00:00:00.000000

Owner-reported bug: Inventory Valuation vs GL Reconciliation off by SAR
31,250.56 on a real company. Root cause, found by replaying every
stock_move against the GL: `receive_stock`'s moving-average formula (see
`InventoryValuationService.receive_stock`) has one genuinely
unrepresentable case -- a receipt that brings a negative position to
EXACTLY zero. The blended value at that instant can be any nonzero
number (the negative position's average cost and the receipt's cost are
independent), but `qty_on_hand` is now 0, and `0 * moving_avg_cost == 0`
regardless of what average is stored -- there is no way to carry a
nonzero value at zero quantity in a qty*avg costing model. That value
already flowed through the GL (every receive/issue posts its own exact
amount), so leaving it out of the register (the old behavior) opened a
permanent gap between the register and the GL.

Fix (this migration's counterpart in application code):
`receive_stock` now returns this "valuation_variance" instead of
silently dropping it, and every caller posts it against this new
"Inventory Valuation Variance" (5150) account -- Dr/Cr Inventory
Valuation Variance vs Dr/Cr Inventory for the exact residual, so the GL
is corrected to match the register instead of the register trying (and
mathematically failing) to match the GL.

Seeds 5150 into every EXISTING company's Chart of Accounts (new
companies get it from DEFAULT_SAUDI_COA going forward) -- same
"backfill from the data itself" approach a4b5c6d7e8f9 used for the
Fixed Assets accounts, so a company onboarded before this fix shipped
doesn't have to hand-create it before the fix can post to it.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE account NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        INSERT INTO account (id, company_id, code, name, name_ar, account_type_id, parent_id, level, is_group)
        SELECT gen_random_uuid(), parent.company_id, '5150', 'Inventory Valuation Variance', 'فروقات تقييم المخزون',
               (SELECT id FROM account_type WHERE code = 'expense'), parent.id, parent.level + 1, false
        FROM account parent
        WHERE parent.code = '5000' AND parent.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM account existing
              WHERE existing.company_id = parent.company_id AND existing.code = '5150'
          )
        """
    )
    op.execute("ALTER TABLE account FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE account NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM account WHERE code = '5150' AND deleted_at IS NULL")
    op.execute("ALTER TABLE account FORCE ROW LEVEL SECURITY")
