"""invoice email delivery

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-08-07 00:00:00.000000

Document Delivery (Product Owner audit, next-highest-value gap after
Approval Workflow): no email-sending mechanism existed anywhere in the
system, and no real PDF existed for the sales invoice document itself
(the Standard Reporting Framework only ever covered tabular reports).
`last_emailed_at`/`last_emailed_to` mirror what every reference ERP shows
on an invoice ("Emailed 2026-08-07 to customer@example.com") — a real,
user-visible confirmation the send actually happened, not just a fire-
and-forget action with no trace.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a6b7c8d9e0f1'
down_revision: Union[str, None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sales_invoice", sa.Column("last_emailed_at", sa.DateTime(), nullable=True))
    op.add_column("sales_invoice", sa.Column("last_emailed_to", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_invoice", "last_emailed_to")
    op.drop_column("sales_invoice", "last_emailed_at")
