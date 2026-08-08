"""product pricing tiers and last purchase price

Revision ID: e5f6a7b8c9d0
Revises: d9e0f1a2b3c4
Create Date: 2026-08-08 00:00:00.000000

Owner-requested (live, applied across all companies):
1. Purchase Order lines should default to the product's last purchase
   price instead of starting at 0 every time - price_high/price_low give
   the buyer nothing to negotiate off of otherwise.
2. The product master should carry 3 reference sale prices (high/medium/
   low) instead of a single figure, matching the tiered price-list pattern
   in SAP B1/Odoo - sales_price remains the medium/default price used to
   pre-fill quotation lines.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd9e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product", sa.Column("last_purchase_price", sa.Numeric(18, 4), nullable=True))
    op.add_column("product", sa.Column("price_high", sa.Numeric(18, 4), nullable=True))
    op.add_column("product", sa.Column("price_low", sa.Numeric(18, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("product", "price_low")
    op.drop_column("product", "price_high")
    op.drop_column("product", "last_purchase_price")
