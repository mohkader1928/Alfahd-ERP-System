"""backfill last_purchase_price from purchase order history

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-08 00:00:00.000002

Owner-reported (live): a real product with plenty of purchase history
still showed no default price on a new Purchase Order line. Root cause:
product.last_purchase_price (migration e5f6a7b8c9d0) only ever gets set
going FORWARD, the moment a new Purchase Order line is created for that
product - it was never backfilled from purchase orders that already
existed before that migration landed. For a company with real purchase
history predating this feature, every product's last_purchase_price
stayed NULL until someone happened to buy it again after the deploy.
Backfills each product's last_purchase_price from its most recent
purchase_order_line (by order_date, then created_at, as a tiebreak),
matching the exact ordering the prospective code already uses ("the
latest one wins").

`product` and `purchase_order_line` both carry FORCE ROW LEVEL
SECURITY keyed on `app.current_company_id` (see docs/16a) — a plain
cross-company UPDATE...FROM with no company context set matches zero
rows, exactly the same silent-no-op trap already documented in
migration d3e4f5a6b7c8. `erp_migrate` (the role Alembic runs as) is
NOBYPASSRLS by design (see bootstrap_db_roles.py) but does own both
tables, so a normal owner would already be exempt from RLS if not for
FORCE — temporarily lifting FORCE ROW LEVEL SECURITY for the duration
of this migration (owner-only DDL, no superuser needed) and restoring
it immediately after is the same pattern migration
8957d3c39d54 already uses for its own cross-tenant backfill.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE product NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE purchase_order_line NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE purchase_order NO FORCE ROW LEVEL SECURITY")
    try:
        op.execute(
            """
            UPDATE product p
            SET last_purchase_price = latest.unit_price
            FROM (
                SELECT DISTINCT ON (pol.product_id, pol.company_id)
                    pol.product_id,
                    pol.company_id,
                    pol.unit_price
                FROM purchase_order_line pol
                JOIN purchase_order po ON po.id = pol.purchase_order_id
                ORDER BY pol.product_id, pol.company_id, po.order_date DESC, po.created_at DESC
            ) AS latest
            WHERE p.id = latest.product_id
              AND p.company_id = latest.company_id
              AND p.last_purchase_price IS NULL
            """
        )
    finally:
        op.execute("ALTER TABLE product FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE purchase_order_line FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE purchase_order FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Irreversible data backfill - no-op downgrade (mirrors the existing
    # convention for this repo's other data-only migrations).
    pass
