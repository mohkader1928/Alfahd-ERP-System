"""partner code

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-08-12 00:00:00.000000

Owner directive: every master-data entity's business identifier must be
system-assigned, guaranteed unique, and never left to the user to type —
FixedAsset.asset_code and (as of this same request) Product.sku already
work this way; Partner (Customer/Vendor/Employee/Contact — one unified
table) had NO business code at all until now. Added as `partner_code`
("PTR-000001" style, one shared sequence regardless of role, since a
single Partner row can hold several roles at once).

Backfill (for any pre-existing environment with real partner rows):
assigns each existing partner within a company a sequential code in
`created_at` order, so pre-request data is brought into compliance rather
than left behind, same as the Owner asked. Column is added nullable,
backfilled, then tightened to NOT NULL — the standard safe-migration
sequence for a new required column on a populated table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("partner", sa.Column("partner_code", sa.Text(), nullable=True))

    # `partner` has FORCE ROW LEVEL SECURITY (f81e8530ddbd) — a plain UPDATE
    # here would be filtered down to whatever single company_id happens to
    # be set in the migration session's GUC (usually none), silently
    # backfilling zero rows and leaving the later NOT NULL/unique steps to
    # fail. Same "NO FORCE for the bulk cross-company write, FORCE right
    # after" bracketing a4b5c6d7e8f9 already uses for `account`.
    op.execute("ALTER TABLE partner NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        WITH numbered AS (
            SELECT id, 'PTR-' || lpad(
                (row_number() OVER (PARTITION BY company_id ORDER BY created_at, id))::text, 6, '0'
            ) AS code
            FROM partner
        )
        UPDATE partner
        SET partner_code = numbered.code
        FROM numbered
        WHERE partner.id = numbered.id
        """
    )
    op.execute("ALTER TABLE partner FORCE ROW LEVEL SECURITY")

    op.alter_column("partner", "partner_code", nullable=False)
    op.create_index("ux_partner_code", "partner", ["company_id", "partner_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_partner_code", table_name="partner")
    op.drop_column("partner", "partner_code")
