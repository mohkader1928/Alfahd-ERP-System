"""Commercial Performance Stage 2B — sales representative transaction snapshot

Revision ID: 656ce42660aa
Revises: 1954ea58d959
Create Date: 2026-08-30 00:00:00.000000

Purely additive, approved Stage 2B scope only:

Three new nullable FK columns, mirroring warehouse_id/cost_center_id's
existing copy-forward pattern exactly:

- quotation.sales_rep_id
- sales_order.sales_rep_id
- sales_invoice.sales_rep_id

All reference sales_representative.id (Stage 2A). No new table, no RLS
change — quotation/sales_order/sales_invoice already carry the
`company_isolation` policy from earlier migrations.

No backfill: every existing row keeps sales_rep_id = NULL
("Unattributed / Legacy"), so all existing records and workflows keep
working exactly as before this stage. Only newly created/confirmed/issued
documents receive real attribution going forward.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '656ce42660aa'
down_revision: Union[str, None] = '1954ea58d959'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quotation",
        sa.Column(
            "sales_rep_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_representative.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "sales_order",
        sa.Column(
            "sales_rep_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_representative.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "sales_invoice",
        sa.Column(
            "sales_rep_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_representative.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("sales_invoice", "sales_rep_id")
    op.drop_column("sales_order", "sales_rep_id")
    op.drop_column("quotation", "sales_rep_id")
