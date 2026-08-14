"""warehouse_id on quotation, sales_order, sales_invoice, purchase_order

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-08-14 00:00:00.000000

Owner request: Quotation, Sales Order, Sales Invoice and Purchase Order
previously had no warehouse of their own at all — every actual stock
movement they triggered (SalesInvoiceService._deduct_stock_for_lines,
GoodsReceiptService.record_receipt) silently used
WarehouseRepository.get_default_for_company() regardless of how many
warehouses the company actually has. Nullable (not backfilled): existing
rows keep working exactly as before via that same default-warehouse
fallback in the application code; only newly created documents are
required (at the Pydantic layer) to carry a real warehouse_id going
forward.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quotation", sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("sales_order", sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("sales_invoice", sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("purchase_order", sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("purchase_order", "warehouse_id")
    op.drop_column("sales_invoice", "warehouse_id")
    op.drop_column("sales_order", "warehouse_id")
    op.drop_column("quotation", "warehouse_id")
