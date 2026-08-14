"""quotation email delivery + partner/quotation payment terms

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-14 00:00:00.000000

Owner request: quotations sent to a customer should carry the payment
terms from the customer's master record, editable per-quotation (the
customer's own value is just the default), and track when/to whom a
quotation was last emailed — mirrors SalesInvoice.last_emailed_at/
last_emailed_to (migration for Document Delivery) exactly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("partner", sa.Column("payment_terms", sa.Text(), nullable=True))
    op.add_column("quotation", sa.Column("payment_terms", sa.Text(), nullable=True))
    op.add_column("quotation", sa.Column("last_emailed_at", sa.DateTime(), nullable=True))
    op.add_column("quotation", sa.Column("last_emailed_to", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("quotation", "last_emailed_to")
    op.drop_column("quotation", "last_emailed_at")
    op.drop_column("quotation", "payment_terms")
    op.drop_column("partner", "payment_terms")
