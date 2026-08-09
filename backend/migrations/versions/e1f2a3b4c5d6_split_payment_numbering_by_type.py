"""split payment numbering by type (customer receipts vs vendor payments)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-09 00:00:00.000002

Owner directive: customer receipts and vendor payments must be visibly
distinct documents with their own sequence, not two flavors of one
shared "PAY-" counter -- so from here on customer receipts number as
RCT-000001, 000002, ... and vendor payments keep numbering as
PAY-000001, 000002, ... but scoped to vendor payments only (previously
the counter mixed both types together, so a company's vendor payments
had gaps like PAY-000001, PAY-000003, PAY-000005 wherever a customer
payment fell in between).

Backfills every existing payment's number to the new per-(company,
payment_type) scheme, preserving each payment's original relative
order (by payment_date, then id as a tiebreaker) within its own type.
Two-phase update (temp value, then final) because a single UPDATE
against the (company_id, number) unique index can transiently collide
mid-statement even though the final state is fully valid -- vendor
payments in particular can have their numeric suffix shift downward
once customer payments are removed from the shared count.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE payment NO FORCE ROW LEVEL SECURITY")

    op.execute("UPDATE payment SET number = 'TMP-' || id::text")

    op.execute(
        """
        WITH ranked AS (
            SELECT id, payment_type,
                   ROW_NUMBER() OVER (
                       PARTITION BY company_id, payment_type ORDER BY payment_date, id
                   ) AS rn
            FROM payment
        )
        UPDATE payment p
        SET number = (CASE WHEN ranked.payment_type = 'customer' THEN 'RCT-' ELSE 'PAY-' END)
            || LPAD(ranked.rn::text, 6, '0')
        FROM ranked
        WHERE p.id = ranked.id
        """
    )

    op.execute("ALTER TABLE payment FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Not meaningfully reversible -- the original shared interleaved
    # order is lost. Best-effort: restore a single PAY- sequence per
    # company, ordered the same way (payment_date, id).
    op.execute("ALTER TABLE payment NO FORCE ROW LEVEL SECURITY")

    op.execute("UPDATE payment SET number = 'TMP-' || id::text")

    op.execute(
        """
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY payment_date, id) AS rn
            FROM payment
        )
        UPDATE payment p
        SET number = 'PAY-' || LPAD(ranked.rn::text, 6, '0')
        FROM ranked
        WHERE p.id = ranked.id
        """
    )

    op.execute("ALTER TABLE payment FORCE ROW LEVEL SECURITY")
