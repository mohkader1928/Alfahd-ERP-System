"""Moving average cost precision + backfill

Standard SME ERP -- Inventory GL/Valuation reconciliation fix (2026-08-19),
reported directly by the Owner against شركة المحمود's real data: the
Inventory Valuation report and the Trial Balance's Inventory (1300) balance
disagreed by ~11,000 SAR on an ~85M SAR balance.

Root cause (verified against real data before writing this migration --
and revised once during investigation, see below):
`stock_quant.qty_on_hand` matched its `stock_move` ledger EXACTLY (615,850
units both ways), and the ledger's own value total matched the GL EXACTLY
(85,264,240.78 both ways) -- ruling out any missing/extra movement or
posting. The gap was purely in `moving_avg_cost`.

Two distinct causes, found in this order:
1. `receive_stock` recomputes the average iteratively on every receipt,
   using the PREVIOUSLY STORED (already-rounded) average as its own
   input -- and the column was NUMERIC(18,4). This compounds a small
   rounding error across many receipts. Real, but only closed a few
   cents of the observed gap once fixed alone.
2. The actual dominant cause: `receive_stock`'s old guard
   (`if new_total_qty > 0:`) SILENTLY DROPS a receipt's entire value
   from the average whenever the position is still zero-or-negative
   after that receipt (a product oversold via FR-INV-007's
   allow_negative path, not yet fully replenished) -- qty_on_hand still
   updates correctly, but the receipt's cost never enters
   moving_avg_cost, permanently understating valuation by that
   receipt's full value. Found on a real company: one product driven to
   -25,000 units by five large vendor returns, then a further receipt
   that still left it at -24,000 -- that receipt's entire value vanished
   from the report while the GL correctly kept it. The corrected guard
   (`!= 0`) preserves the algebraic identity `new_total_qty *
   new_avg == old_qty*old_avg + qty*unit_cost` for any sign of
   new_total_qty, which is what makes qty*avg_cost conserve the GL's
   cumulative net value exactly, in negative territory or not.

This migration:
1. Widens `stock_quant.moving_avg_cost` to NUMERIC(18,6) (matches the
   application-code fix in the same commit, which now explicitly
   quantizes to six decimal places instead of relying on the column's
   implicit truncation).
2. Backfills every existing `average`-valuation-method company's
   `stock_quant` rows by REPLAYING that same product/location's real
   `stock_move` history in chronological order with the CORRECTED
   formula (point 2 above) at six-decimal-place precision (point 1) --
   not inventing a number, recomputing the exact figure the corrected
   code would have produced had it been running from day one.
   `fifo`-method companies are untouched: `moving_avg_cost` is never
   read for FIFO (StockLayer carries the real cost basis instead), so
   there is nothing to correct there.

Revision ID: c9f1a2b3d4e5
Revises: e4add2e2d6c4
Create Date: 2026-08-19
"""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "c9f1a2b3d4e5"
down_revision: str | None = "e4add2e2d6c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIX_DP = Decimal("0.000001")


def upgrade() -> None:
    op.alter_column(
        "stock_quant",
        "moving_avg_cost",
        type_=sa.Numeric(18, 6),
        existing_type=sa.Numeric(18, 4),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )

    # Bulk cross-company backfill with no app.current_company_id set --
    # same NO FORCE/FORCE bracket the is_cash_equivalent/company.code
    # precedents use.
    op.execute("ALTER TABLE company NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE stock_move NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE stock_quant NO FORCE ROW LEVEL SECURITY")

    conn = op.get_bind()

    company_ids = [
        row[0]
        for row in conn.execute(
            sa.text("SELECT id FROM company WHERE valuation_method = 'average'")
        ).fetchall()
    ]

    for company_id in company_ids:
        quant_rows = conn.execute(
            sa.text("SELECT id, product_id, location_id FROM stock_quant WHERE company_id = :cid"),
            {"cid": company_id},
        ).fetchall()

        for quant_id, product_id, location_id in quant_rows:
            moves = conn.execute(
                sa.text(
                    """
                    SELECT qty, unit_cost, dest_location_id
                    FROM stock_move
                    WHERE company_id = :cid
                      AND product_id = :pid
                      AND (dest_location_id = :lid OR source_location_id = :lid)
                    ORDER BY moved_at, id
                    """
                ),
                {"cid": company_id, "pid": product_id, "lid": location_id},
            ).fetchall()

            running_qty = Decimal("0")
            running_avg = Decimal("0")
            for qty, unit_cost, dest_location_id in moves:
                qty = Decimal(qty)
                if dest_location_id is not None:
                    # Receipt -- exactly mirrors receive_stock's own
                    # (corrected) formula: `!= 0`, not `> 0` -- see this
                    # migration's own docstring for why the value must
                    # never be silently dropped just because the position
                    # is still negative after this receipt.
                    new_total_qty = running_qty + qty
                    if new_total_qty != 0:
                        running_avg = (
                            (running_qty * running_avg) + (qty * Decimal(unit_cost))
                        ) / new_total_qty
                        running_avg = running_avg.quantize(SIX_DP, rounding=ROUND_HALF_UP)
                    running_qty = new_total_qty
                else:
                    # Issue -- reduces quantity only, average is untouched
                    # (matches issue_stock, which never rewrites moving_avg_cost).
                    running_qty -= qty

            conn.execute(
                sa.text("UPDATE stock_quant SET moving_avg_cost = :avg WHERE id = :qid"),
                {"avg": running_avg, "qid": quant_id},
            )

    op.execute("ALTER TABLE stock_quant FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE stock_move FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE company FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.alter_column(
        "stock_quant",
        "moving_avg_cost",
        type_=sa.Numeric(18, 4),
        existing_type=sa.Numeric(18, 6),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
    )
