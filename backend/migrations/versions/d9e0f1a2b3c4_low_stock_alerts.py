"""low stock alerts

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-08-09 00:00:00.000000

Product Owner audit (full-system re-audit after the concurrency/
idempotency pass): "what's below reorder point right now?" is a
table-stakes feature in every reference ERP (SAP B1, Dynamics 365 BC,
Odoo) and was entirely absent here - no reorder-point field on the
product master at all, confirmed by grep. Reuses the existing
Notifications module (Approval Workflow bundle) for delivery rather than
building a second alerting mechanism.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product", sa.Column("reorder_point", sa.Numeric(18, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("product", "reorder_point")
