"""vendor debit note

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-08 00:00:00.000003

Product Owner audit: Sales already has a Credit Note (a document that
reverses a posted invoice, reducing what a customer owes) but
Purchasing has no equivalent for reversing a posted vendor bill
(returning goods to a vendor, or a price correction) — a real
asymmetry against SAP B1/Dynamics 365 BC/Odoo, all of which support
vendor debit notes as a first-class document. Mirrors
sales_invoice.invoice_type/original_invoice_id exactly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vendor_bill",
        sa.Column("bill_type", sa.Text(), nullable=False, server_default="standard"),
    )
    op.add_column(
        "vendor_bill",
        sa.Column("original_bill_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_vendor_bill_type",
        "vendor_bill",
        "bill_type IN ('standard', 'debit_note')",
    )
    op.create_foreign_key(
        "vendor_bill_original_bill_id_fkey",
        "vendor_bill",
        "vendor_bill",
        ["original_bill_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("vendor_bill_original_bill_id_fkey", "vendor_bill", type_="foreignkey")
    op.drop_constraint("ck_vendor_bill_type", "vendor_bill", type_="check")
    op.drop_column("vendor_bill", "original_bill_id")
    op.drop_column("vendor_bill", "bill_type")
