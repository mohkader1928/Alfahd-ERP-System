"""Make vendor_bill.purchase_order_id and vendor_bill_line.purchase_order_line_id nullable

Revision ID: b3c4d5e6f7a8
Revises: f3a4b5c6d7e8
Create Date: 2026-08-11 00:00:01.000000

Product Owner request: a Purchase Return should not have to correspond to
one whole vendor bill (or even one purchase order) — it can be a freeform
set of lines, with the original bill number reduced to an OPTIONAL
traceability field. Every existing debit note today inherits its
purchase_order_id from an original bill's own, and every existing bill
line inherits a real purchase_order_line_id from 3-way matching — neither
of those exist for a freeform return with no original document at all, so
both columns must accept NULL. Standard bills (bill_type='standard') are
untouched: the application layer, not this constraint, keeps requiring a
real PO for that path.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("vendor_bill", "purchase_order_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.alter_column(
        "vendor_bill_line", "purchase_order_line_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        "vendor_bill_line", "purchase_order_line_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False
    )
    op.alter_column("vendor_bill", "purchase_order_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
