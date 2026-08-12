"""Sales order partial invoicing: add 'partially_invoiced' status, drop
the one-invoice-per-order unique constraint

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-11 00:00:02.000000

Product Owner-reported blocker: a Sales Order for a quantity larger than
what's currently in stock has no way forward today — invoicing the whole
order at once fails outright on InsufficientStockError, and the order
itself has no edit path either, leaving it stuck forever. Standard ERP
practice (SAP/Oracle/Odoo) is partial fulfillment: invoice what's
available now, leave the rest as an open backorder to invoice later once
stock (e.g. a pending Purchase Order) arrives.

This requires two schema changes:
  1. `sales_order.status` gains 'partially_invoiced' (mirrors
     purchase_order's own status set, which already needed
     'partially_received'/'partially_billed' for the identical reason on
     the Purchasing side).
  2. `ux_sales_invoice_sales_order_id` — a UNIQUE index that was the
     concurrency guard for the old all-or-nothing "one invoice per
     order" design — is dropped and replaced with a plain (non-unique)
     index. Multiple invoices against the same order (one per backorder
     release) are now a legitimate, expected shape; the new concurrency
     guard is a row lock on each SalesOrderLine when qty_invoiced is
     incremented (mirrors PurchaseOrderLine's existing
     qty_received/qty_billed row-lock pattern), not a DB-level
     uniqueness constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_STATUSES = ("draft", "confirmed", "done", "cancelled")
NEW_STATUSES = ("draft", "confirmed", "partially_invoiced", "done", "cancelled")


def upgrade() -> None:
    op.drop_constraint("ck_sales_order_status", "sales_order", type_="check")
    op.create_check_constraint("ck_sales_order_status", "sales_order", f"status IN {NEW_STATUSES}")
    op.add_column("sales_order", sa.Column("cancellation_reason", sa.Text(), nullable=True))

    op.drop_index("ux_sales_invoice_sales_order_id", table_name="sales_invoice")
    op.create_index(
        "ix_sales_invoice_sales_order_id",
        "sales_invoice",
        ["sales_order_id"],
        unique=False,
        postgresql_where=sa.text("sales_order_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_sales_invoice_sales_order_id", table_name="sales_invoice")
    op.create_index(
        "ux_sales_invoice_sales_order_id",
        "sales_invoice",
        ["sales_order_id"],
        unique=True,
        postgresql_where=sa.text("sales_order_id IS NOT NULL"),
    )

    op.drop_column("sales_order", "cancellation_reason")
    op.drop_constraint("ck_sales_order_status", "sales_order", type_="check")
    op.create_check_constraint("ck_sales_order_status", "sales_order", f"status IN {OLD_STATUSES}")
