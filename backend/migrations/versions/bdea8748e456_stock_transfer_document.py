"""stock transfer as a real document

Revision ID: bdea8748e456
Revises: c5d6e7f8a9b0
Create Date: 2026-08-25 00:00:00.000000

A transfer between two locations was previously two fire-and-forget
StockMove rows sharing a throwaway, never-persisted UUID -- no document a
user could look up, list, or link to. This adds `stock_transfer` (header)
and `stock_transfer_line` (one line per transfer today, matching the
existing single-product-per-call create flow unchanged) so a transfer
becomes a real, numbered ("TRF-000001"), listable, linkable document --
same shape as cycle_count/cycle_count_line, and both tables get their own
company_id + RLS policy directly from creation (the hardened pattern from
Phase 16A, not the older join-through-parent-only approach cycle_count_line
originally shipped with).

Purely additive: two new tables, no existing table touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bdea8748e456'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["stock_transfer", "stock_transfer_line"]


def upgrade() -> None:
    op.create_table(
        'stock_transfer',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('source_warehouse_id', sa.UUID(), nullable=False),
        sa.Column('dest_warehouse_id', sa.UUID(), nullable=False),
        sa.Column('number', sa.Text(), nullable=False),
        sa.Column('transfer_date', sa.Date(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['source_warehouse_id'], ['warehouse.id']),
        sa.ForeignKeyConstraint(['dest_warehouse_id'], ['warehouse.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stock_transfer_company_id', 'stock_transfer', ['company_id'])

    op.create_table(
        'stock_transfer_line',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('stock_transfer_id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('source_location_id', sa.UUID(), nullable=False),
        sa.Column('dest_location_id', sa.UUID(), nullable=False),
        sa.Column('qty', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('issue_move_id', sa.UUID(), nullable=True),
        sa.Column('receive_move_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['stock_transfer_id'], ['stock_transfer.id']),
        sa.ForeignKeyConstraint(['source_location_id'], ['location.id']),
        sa.ForeignKeyConstraint(['dest_location_id'], ['location.id']),
        sa.ForeignKeyConstraint(['issue_move_id'], ['stock_move.id']),
        sa.ForeignKeyConstraint(['receive_move_id'], ['stock_move.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stock_transfer_line_company_id', 'stock_transfer_line', ['company_id'])

    for table in TABLES:
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
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index('ix_stock_transfer_line_company_id', table_name='stock_transfer_line')
    op.drop_table('stock_transfer_line')
    op.drop_index('ix_stock_transfer_company_id', table_name='stock_transfer')
    op.drop_table('stock_transfer')
