"""Vendor bill warehouse + backfill credit note warehouse

Standard SME ERP -- Owner request (2026-08-20): the warehouse a document's
goods relate to must be visible on Purchase Order, Vendor Bill, Quotation,
Sales Order, and Sales Invoice, for the warehouse keeper, accountant, and
auditor. Quotation/Sales Order/standard Sales Invoice/standard Vendor Bill
already carry `warehouse_id` (or now do, via the application-code change
in this same commit) -- this migration covers the two gaps that needed a
real schema/data change:

1. `vendor_bill.warehouse_id` did not exist at all. Additive, nullable
   column. Backfilled for every existing bill that has a resolvable
   `purchase_order_id` (standard bills, and debit notes issued against a
   bill that itself had a PO) by copying `purchase_order.warehouse_id` --
   not invented, joined from real, already-stored data. Freeform Purchase
   Returns with no PO and no traceable original bill are left NULL --
   there is genuinely nothing to infer that from.

2. `sales_invoice.warehouse_id` already exists but was never populated for
   credit notes (`issue_credit_note`/`issue_credit_note_for_lines` simply
   never set it). Backfilled for every existing credit note that has a
   resolvable `original_invoice_id` by copying that invoice's own
   `warehouse_id`. Freeform Sales Returns with no original invoice are
   left NULL for the same reason as above.

Revision ID: f7a8b9c0d1e2
Revises: c9f1a2b3d4e5
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "c9f1a2b3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vendor_bill",
        sa.Column(
            "warehouse_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("warehouse.id"), nullable=True
        ),
    )

    # Bulk cross-company backfill -- same NO FORCE/FORCE bracket used by
    # every prior precedent in this codebase (is_cash_equivalent, moving
    # average cost, etc).
    op.execute("ALTER TABLE vendor_bill NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales_invoice NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE purchase_order NO FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        UPDATE vendor_bill
        SET warehouse_id = po.warehouse_id
        FROM purchase_order po
        WHERE vendor_bill.purchase_order_id = po.id
          AND po.warehouse_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE sales_invoice
        SET warehouse_id = original.warehouse_id
        FROM sales_invoice original
        WHERE sales_invoice.original_invoice_id = original.id
          AND sales_invoice.warehouse_id IS NULL
          AND original.warehouse_id IS NOT NULL
        """
    )

    op.execute("ALTER TABLE purchase_order FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales_invoice FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE vendor_bill FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_column("vendor_bill", "warehouse_id")
