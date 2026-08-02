"""phase17d_payments_module

Revision ID: 5955ce0f8dd6
Revises: 0fc571b91522
Create Date: 2026-08-02 12:27:01.697799

Phase 17D — Payments. Adds:
  - `due_date` (nullable) on `sales_invoice`/`vendor_bill` — additive,
    no backfill needed.
  - `payment` + `payment_allocation` — new tables, both `company_id`-scoped
    with `company_isolation` RLS applied in this same migration (Phase
    16A/16B had to retrofit this after the fact; not repeating that here).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '5955ce0f8dd6'
down_revision: Union[str, None] = '0fc571b91522'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = ["payment", "payment_allocation"]


def upgrade() -> None:
    op.add_column("sales_invoice", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("vendor_bill", sa.Column("due_date", sa.Date(), nullable=True))

    op.create_table(
        "payment",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_type", sa.Text(), nullable=False),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.Text(), nullable=False, server_default="SAR"),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("payment_type IN ('customer','vendor')", name="ck_payment_type"),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "number", name="ux_payment_number"),
    )
    op.create_index(op.f("ix_payment_company_id"), "payment", ["company_id"], unique=False)
    op.create_index(op.f("ix_payment_partner_id"), "payment", ["partner_id"], unique=False)

    op.create_table(
        "payment_allocation",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sales_invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vendor_bill_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payment_allocation_amount_positive"),
        sa.CheckConstraint(
            "(sales_invoice_id IS NOT NULL AND vendor_bill_id IS NULL) OR "
            "(sales_invoice_id IS NULL AND vendor_bill_id IS NOT NULL)",
            name="ck_payment_allocation_exactly_one_target",
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payment.id"]),
        sa.ForeignKeyConstraint(["sales_invoice_id"], ["sales_invoice.id"]),
        sa.ForeignKeyConstraint(["vendor_bill_id"], ["vendor_bill.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_allocation_company_id"), "payment_allocation", ["company_id"], unique=False)
    op.create_index(op.f("ix_payment_allocation_payment_id"), "payment_allocation", ["payment_id"], unique=False)
    op.create_index(
        op.f("ix_payment_allocation_sales_invoice_id"), "payment_allocation", ["sales_invoice_id"], unique=False
    )
    op.create_index(
        op.f("ix_payment_allocation_vendor_bill_id"), "payment_allocation", ["vendor_bill_id"], unique=False
    )

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY company_isolation ON {table}
            USING (company_id = current_setting('app.current_company_id', true)::uuid)
            WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
            """
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("payment_allocation")
    op.drop_table("payment")
    op.drop_column("vendor_bill", "due_date")
    op.drop_column("sales_invoice", "due_date")
