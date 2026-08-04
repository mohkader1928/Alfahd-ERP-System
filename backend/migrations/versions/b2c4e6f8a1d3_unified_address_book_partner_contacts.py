"""unified address book — partner extensions + partner_address

Revision ID: b2c4e6f8a1d3
Revises: a1b2c3d4e5f6
Create Date: 2026-08-04 00:00:00.000000

Unified Address Book / Partner & Contacts bundle, per the Owner's 15
approval conditions on the proposed design. Two structural decisions worth
recording here since they materially depart from the originally-proposed
plan:

1. No `partner_contact` table. A "contact person" is just another `partner`
   row (`is_company=false`) with `parent_partner_id` pointing at the
   company it belongs to. This directly satisfies the Owner's condition
   that a contact must be able to become an independent Partner (gain
   `is_customer`/`is_vendor`/`is_employee`, its own addresses, etc.)
   *without recreating identity data* — it already IS a Partner row from
   the moment it's created, so "promotion" is just flipping booleans on
   the same row, not a migration. `job_title`/`is_primary_contact` carry
   the small bit of relationship metadata a contact needs.

2. `partner.address` (JSONB) is intentionally NOT dropped in this
   migration, per explicit Owner instruction — kept post-backfill as a
   deprecated, no-longer-written-to column so removal can be a separate,
   lower-risk migration once regression proves nothing still depends on
   it. `partner_address` is a new, generic, FK-able table so Sales/
   Purchasing can later reference specific billing/shipping addresses by
   stable UUID, without needing to change this migration when they do.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b2c4e6f8a1d3'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Partner: master-entity + contact-linkage + contact-info columns ---
    op.add_column("partner", sa.Column("is_company", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column(
        "partner",
        sa.Column("parent_partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partner.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("partner", sa.Column("is_employee", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("partner", sa.Column("job_title", sa.Text(), nullable=True))
    op.add_column("partner", sa.Column("is_primary_contact", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("partner", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column("partner", sa.Column("mobile", sa.Text(), nullable=True))
    op.add_column("partner", sa.Column("email", sa.Text(), nullable=True))
    op.add_column("partner", sa.Column("website", sa.Text(), nullable=True))
    op.create_index("ix_partner_parent", "partner", ["parent_partner_id"])

    # --- partner_address: structured, FK-able, multi-address ---
    op.create_table(
        "partner_address",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partner.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("street", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("postal_code", sa.Text(), nullable=True),
        sa.Column("country_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("type IN ('billing', 'shipping', 'other')", name="ck_partner_address_type"),
    )
    op.create_index("ix_partner_address_company_id", "partner_address", ["company_id"])
    op.create_index("ix_partner_address_partner_id", "partner_address", ["partner_id"])

    op.execute("ALTER TABLE partner_address ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partner_address FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON partner_address
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """
    )

    # --- Backfill: one 'billing' + is_default row per partner that has a
    # populated legacy `address` JSONB blob. `partner.address` itself is
    # deliberately left untouched (see module docstring).
    op.execute(
        """
        INSERT INTO partner_address
            (id, company_id, partner_id, type, is_default, street, city, region, postal_code, country_code, created_at, updated_at)
        SELECT gen_random_uuid(), company_id, id, 'billing', true,
               address->>'street', address->>'city', address->>'region', address->>'postal_code', address->>'country_code',
               now(), now()
        FROM partner
        WHERE address IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON partner_address")
    op.execute("ALTER TABLE partner_address NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partner_address DISABLE ROW LEVEL SECURITY")
    op.drop_table("partner_address")

    op.drop_index("ix_partner_parent", table_name="partner")
    op.drop_column("partner", "website")
    op.drop_column("partner", "email")
    op.drop_column("partner", "mobile")
    op.drop_column("partner", "phone")
    op.drop_column("partner", "is_primary_contact")
    op.drop_column("partner", "job_title")
    op.drop_column("partner", "is_employee")
    op.drop_column("partner", "parent_partner_id")
    op.drop_column("partner", "is_company")
