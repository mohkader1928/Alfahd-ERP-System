"""goods receipt number unique constraint

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-08-08 00:00:00.000000

Concurrency-correctness bundle (docs/16b-idempotency-concurrency-design.md,
finding #5): every other numbered document (quotation, sales_order,
sales_invoice, purchase_order, vendor_bill) already carries
UNIQUE(company_id, number) - goods_receipt was the one document type that
shipped without it, confirmed via direct pg_constraint query to be the
sole numbered document with zero backstop against a duplicate number.
Purely additive; verified zero pre-existing violations before writing
this migration (SELECT company_id, number, count(*) ... HAVING count(*) > 1
returned 0 rows).
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a6b7c8d9e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("ux_goods_receipt_number", "goods_receipt", ["company_id", "number"])


def downgrade() -> None:
    op.drop_constraint("ux_goods_receipt_number", "goods_receipt", type_="unique")
