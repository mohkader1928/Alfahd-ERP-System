"""attachments

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-08-07 00:00:00.000000

Professional Workspace Layer — Attachments. Every reference ERP (Odoo,
SAP B1, Dynamics 365 BC, NetSuite, ERPNext) lets a user attach an
arbitrary file (a scanned PO, a signed delivery note, a vendor's invoice
PDF) to any business document; this system had zero such mechanism
outside the unrelated Entity Media Foundation (company/partner/product
logos only). One polymorphic `attachment` table (`entity_type` +
`entity_id`, matching the same convention `source_table`/`source_id`
already use elsewhere in this codebase — e.g. `stock_move`, journal entry
line drill-down) — not a separate table per document type. `company_id`-
scoped with `company_isolation` RLS applied in this same migration
(the Phase 16A/16B lesson: never bolt RLS on after the fact).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachment",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attachment_entity", "attachment", ["company_id", "entity_type", "entity_id"], unique=False
    )

    op.execute("ALTER TABLE attachment ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE attachment FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY company_isolation ON attachment
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON attachment")
    op.execute("ALTER TABLE attachment NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE attachment DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_attachment_entity", table_name="attachment")
    op.drop_table("attachment")
