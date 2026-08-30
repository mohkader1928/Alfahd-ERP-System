"""Commercial Performance Stage 3 — commission transaction ledger

Revision ID: c3d8e91a4f27
Revises: fb7071e14357
Create Date: 2026-08-30 00:00:00.000000

Purely additive, approved Stage 3 scope only:

New `commission_transaction` table — one immutable row per commission-
bearing event (invoice issuance, credit-note reversal, customer-receipt
collection). Mirrors `journal_entry`'s own `source_table`/`source_id`
polymorphic-reference convention (see migration for `journal_entry`) and
the same `company_isolation` RLS shape already used by every other
company-scoped table (see e.g. `sales_representative`, migration
1954ea58d959).

`commission_rate` is stored on every row so a later change to
`sales_representative.commission_rate` can never retroactively alter a
historical commission figure — each row is written once at the moment of
the underlying event and is never updated again. A credit note writes a
NEW negative-signed row rather than editing the original invoice's row.

`status` defaults to 'calculated' and exists purely for a future
settlement stage's forward compatibility — nothing in Stage 3 ever writes
any other status.

No backfill: this table starts empty. Existing invoices/credit
notes/payments issued before this stage simply never gained a commission
row and are not retroactively commissioned.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c3d8e91a4f27'
down_revision: Union[str, None] = 'fb7071e14357'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commission_transaction",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "representative_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales_representative.id"),
            nullable=False,
        ),
        sa.Column("commission_type", sa.Text(), nullable=False),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("commission_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'calculated'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("commission_type IN ('sales','collection')", name="ck_commission_transaction_type"),
        sa.CheckConstraint(
            "status IN ('calculated','approved','paid','cancelled')", name="ck_commission_transaction_status"
        ),
    )
    op.create_index(
        "ix_commission_transaction_company_id", "commission_transaction", ["company_id"], unique=False
    )
    op.create_index(
        "ix_commission_transaction_source",
        "commission_transaction",
        ["source_table", "source_id"],
        unique=False,
    )
    op.create_index(
        "ix_commission_transaction_company_rep_date",
        "commission_transaction",
        ["company_id", "representative_id", "transaction_date"],
        unique=False,
    )

    op.execute("ALTER TABLE commission_transaction ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE commission_transaction FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON commission_transaction
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON commission_transaction")
    op.execute("ALTER TABLE commission_transaction NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE commission_transaction DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_commission_transaction_company_rep_date", table_name="commission_transaction")
    op.drop_index("ix_commission_transaction_source", table_name="commission_transaction")
    op.drop_index("ix_commission_transaction_company_id", table_name="commission_transaction")
    op.drop_table("commission_transaction")
