"""Phase 17B: unit_of_measure table + product.uom_id

Revision ID: a3f6e2c9d1b4
Revises: 0e71cd2ec945
Create Date: 2026-08-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f6e2c9d1b4'
down_revision: Union[str, None] = '0e71cd2ec945'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'unit_of_measure',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('name_ar', sa.Text(), nullable=True),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_unit_of_measure_company_id'), 'unit_of_measure', ['company_id'], unique=False)
    op.create_index('ux_uom_company_code', 'unit_of_measure', ['company_id', 'code'], unique=True)

    # Same RLS pattern as f81e8530ddbd (Phase 6/M2 partner/product/sales
    # tables) and 8957d3c39d54 (Phase 16A) — every company-scoped table gets
    # ENABLE + FORCE + a company_isolation USING/WITH CHECK policy so
    # isolation holds at the database layer, not just in application filters.
    op.execute("ALTER TABLE unit_of_measure ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE unit_of_measure FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON unit_of_measure
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )

    # Nullable: existing products (502 rows verified pre-migration, none
    # reference a UOM yet) simply get NULL, no backfill needed.
    op.add_column('product', sa.Column('uom_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_product_uom_id'), 'product', ['uom_id'], unique=False)
    op.create_foreign_key('fk_product_uom_id', 'product', 'unit_of_measure', ['uom_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_product_uom_id', 'product', type_='foreignkey')
    op.drop_index(op.f('ix_product_uom_id'), table_name='product')
    op.drop_column('product', 'uom_id')

    op.execute("DROP POLICY IF EXISTS company_isolation ON unit_of_measure")
    op.execute("ALTER TABLE unit_of_measure NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE unit_of_measure DISABLE ROW LEVEL SECURITY")

    op.drop_index('ux_uom_company_code', table_name='unit_of_measure')
    op.drop_index(op.f('ix_unit_of_measure_company_id'), table_name='unit_of_measure')
    op.drop_table('unit_of_measure')
