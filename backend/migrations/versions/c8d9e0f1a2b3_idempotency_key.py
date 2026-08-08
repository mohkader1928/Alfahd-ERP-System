"""idempotency key

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-08 01:00:00.000000

Product Owner audit (docs/16b-idempotency-concurrency-design.md): zero
idempotency mechanism exists anywhere in the backend, confirmed by grep.
A retry-after-timeout of `POST /sales/invoices/{id}:credit-note` (client
never receives the response, retries the identical request) creates a
second, fully independent credit note - a real financial duplication
risk. Unlike sales invoice issuance (already closed via a simple
status-guard + DB constraint), a credit note cannot be closed that way:
issuing a second credit note against the same invoice is a legitimate
business action (partial returns, separate corrections), so "block any
second credit note" would be a functional regression, not a fix. This
table is the shared, reusable mechanism the design doc recommends
(Option B) for that class of endpoint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_key",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="in_progress", nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "idempotency_key", "endpoint", name="ux_idempotency_key"),
        sa.CheckConstraint("status IN ('in_progress','completed','failed')", name="ck_idempotency_key_status"),
    )

    op.execute("ALTER TABLE idempotency_key ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE idempotency_key FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY company_isolation ON idempotency_key
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON idempotency_key")
    op.execute("ALTER TABLE idempotency_key NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE idempotency_key DISABLE ROW LEVEL SECURITY")
    op.drop_table("idempotency_key")
