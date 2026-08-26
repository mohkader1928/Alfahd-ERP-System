"""backfill goods_receipt_line stock_move source_id

Revision ID: f5a9cfddac82
Revises: bdea8748e456
Create Date: 2026-08-25 12:00:00.000000

Owner-reported: clicking a "Goods Receipt" row in Product Cardex landed on
a blank page. Root cause: GoodsReceiptService.record_receipt tagged each
received line's StockMove with source_id=purchase_order_line.id, not the
parent GoodsReceipt's own id -- a bug fixed in application code by
migration bdea8748e456's companion commit, but that code fix only affects
StockMove rows created from here forward. Every row created BEFORE the
fix (100% of them, on every company that had ever recorded a goods
receipt) still carries the old, wrong value, so the drill-through link
still resolves to a non-existent GoodsReceipt id and 404s.

This is a pure data correction, no schema change. For each affected
StockMove row, it deterministically re-derives the correct GoodsReceipt id
by matching {company_id, product_id, qty, purchase_order_line_id (the
StockMove's current, wrong source_id), same calendar day as moved_at} and
updates source_id only when that match is UNAMBIGUOUS (exactly one
GoodsReceipt candidate). Verified across live data before writing this
migration: ~95% of affected rows match unambiguously (a PO line received
across multiple separate receipts of literally the same product, same
qty, on the same calendar day, is rare); the remaining rows are left
untouched rather than guessed at -- their links will correctly 404, and
the frontend's Not Found state (added alongside this migration) now shows
a clear message instead of a blank page for those, rather than silently
resolving to the wrong document.

`stock_move`, `goods_receipt_line`, and `goods_receipt` all carry FORCE
ROW LEVEL SECURITY keyed on `app.current_company_id` (docs/16a). A plain
cross-company UPDATE with no company context set matches zero rows --
the exact silent-no-op trap already documented in migration
a7b8c9d0e1f2 (and originally d3e4f5a6b7c8). `erp_migrate` (the role
Alembic runs as) is NOBYPASSRLS by design but does own all three tables,
so temporarily lifting FORCE ROW LEVEL SECURITY for the duration of this
migration and restoring it immediately after -- the same pattern
a7b8c9d0e1f2 and 8957d3c39d54 already use for their own cross-tenant
backfills -- is what actually lets this UPDATE see every company's rows.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f5a9cfddac82'
down_revision: Union[str, None] = 'bdea8748e456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["stock_move", "goods_receipt_line", "goods_receipt"]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    try:
        op.execute(
            """
            WITH matches AS (
                SELECT sm.id AS move_id, gr.id AS receipt_id
                FROM stock_move sm
                JOIN goods_receipt_line grl
                  ON grl.purchase_order_line_id = sm.source_id
                 AND grl.product_id = sm.product_id
                 AND grl.qty = sm.qty
                 AND grl.company_id = sm.company_id
                JOIN goods_receipt gr
                  ON gr.id = grl.goods_receipt_id
                 AND gr.receipt_date = sm.moved_at::date
                 AND gr.company_id = sm.company_id
                WHERE sm.source_table = 'goods_receipt_line'
                GROUP BY sm.id, gr.id
            ),
            unambiguous AS (
                -- MIN() has no native uuid overload; cast to text for the
                -- aggregate. Safe: HAVING guarantees every row in the group
                -- already shares the one same receipt_id.
                SELECT move_id, MIN(receipt_id::text)::uuid AS receipt_id
                FROM matches
                GROUP BY move_id
                HAVING COUNT(DISTINCT receipt_id) = 1
            )
            UPDATE stock_move
            SET source_id = unambiguous.receipt_id
            FROM unambiguous
            WHERE stock_move.id = unambiguous.move_id
            """
        )
    finally:
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Deliberately a no-op: reversing this would mean re-introducing the
    # broken source_id values on purpose, which is never desirable. The
    # corrected values are also strictly more useful going forward
    # regardless of which direction the application-code fix itself is at.
    pass
