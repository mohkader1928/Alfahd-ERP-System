"""approval workflow and notifications

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-08-07 00:00:00.000000

Product Owner directive: stop adding standalone report screens, close the
single highest-value gap instead. Full-system audit found the gap
explicitly flagged (not silently missing) in
`purchasing/application/services.py`'s own docstring: "Approval routing
(FR-CORE-052, 'PO amount exceeds threshold') is deferred — the nucleus
auto-confirms every PO." Every reference ERP (SAP B1, Dynamics 365 BC,
Odoo, ERPNext) gates spend above a threshold behind an approval step; this
system had none. Paired with a companion Notifications gap (also
confirmed entirely absent) since an approval request with no way to alert
the approver is half a feature.

Scoped to Purchase Orders only (the canonical "PO needs approval" case
every one of those reference systems ships first) — Sales Orders/Journal
Entries are flagged as follow-on candidates, not built here, to keep this
bundle's blast radius reviewable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Company-level approval policy -------------------------------------
    op.add_column("company", sa.Column("po_approval_threshold", sa.Numeric(18, 4), nullable=True))

    # --- Purchase Order approval fields --------------------------------------
    op.add_column("purchase_order", sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "purchase_order",
        sa.Column("approval_status", sa.Text(), nullable=False, server_default="not_required"),
    )
    op.add_column("purchase_order", sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("purchase_order", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("purchase_order", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_purchase_order_created_by", "purchase_order", "app_user", ["created_by_user_id"], ["id"]
    )
    op.create_foreign_key("fk_purchase_order_approved_by", "purchase_order", "app_user", ["approved_by"], ["id"])

    op.drop_constraint("ck_purchase_order_status", "purchase_order", type_="check")
    op.create_check_constraint(
        "ck_purchase_order_status",
        "purchase_order",
        "status IN ('draft','pending_approval','confirmed','done','cancelled')",
    )
    op.create_check_constraint(
        "ck_purchase_order_approval_status",
        "purchase_order",
        "approval_status IN ('not_required','pending','approved','rejected')",
    )

    # --- Notifications --------------------------------------------------------
    op.create_table(
        "notification",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_recipient",
        "notification",
        ["company_id", "recipient_user_id", "is_read", "created_at"],
        unique=False,
    )

    op.execute("ALTER TABLE notification ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY company_isolation ON notification
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_isolation ON notification")
    op.execute("ALTER TABLE notification NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_notification_recipient", table_name="notification")
    op.drop_table("notification")

    op.drop_constraint("ck_purchase_order_approval_status", "purchase_order", type_="check")
    op.drop_constraint("ck_purchase_order_status", "purchase_order", type_="check")
    op.create_check_constraint(
        "ck_purchase_order_status", "purchase_order", "status IN ('draft','confirmed','done','cancelled')"
    )
    op.drop_constraint("fk_purchase_order_approved_by", "purchase_order", type_="foreignkey")
    op.drop_constraint("fk_purchase_order_created_by", "purchase_order", type_="foreignkey")
    op.drop_column("purchase_order", "rejection_reason")
    op.drop_column("purchase_order", "approved_at")
    op.drop_column("purchase_order", "approved_by")
    op.drop_column("purchase_order", "approval_status")
    op.drop_column("purchase_order", "created_by_user_id")

    op.drop_column("company", "po_approval_threshold")
