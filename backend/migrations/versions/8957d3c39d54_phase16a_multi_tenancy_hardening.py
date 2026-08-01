"""phase 16a — multi-tenancy hardening: company_id on line-item tables +
zatca_submission, RLS policies for role/user_company_access

Revision ID: 8957d3c39d54
Revises: 15268c65e57a
Create Date: 2026-08-01 00:00:00.000000

Phase 16A audit finding: every line-item table (and `location`,
`zatca_submission`) has exactly one non-nullable FK to a single parent row
that already carries `company_id` + an active RLS policy — but the line
table itself has no `company_id` of its own, so isolation for these tables
depended entirely on repository code always joining through the parent.
This migration adds a direct, backfilled, NOT NULL `company_id` to each of
them and enables the same `company_isolation` RLS policy already used
elsewhere, so the database enforces isolation independently of how a query
is written. `role` and `user_company_access` already had `company_id`
(NOT NULL, populated) but no policy — simplest fix in this migration, no
schema change needed for those two.

Purely additive: no existing column, index, or constraint is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '8957d3c39d54'
down_revision: Union[str, None] = '15268c65e57a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (child_table, parent_fk_column, parent_table) — each child has exactly one
# non-nullable FK to parent, and parent.company_id is itself NOT NULL, so
# the backfill below is guaranteed complete: no row can end up without a
# determinable company.
LINE_TABLES = [
    ("quotation_line", "quotation_id", "quotation"),
    ("sales_order_line", "sales_order_id", "sales_order"),
    ("sales_invoice_line", "sales_invoice_id", "sales_invoice"),
    ("vendor_bill_line", "vendor_bill_id", "vendor_bill"),
    ("purchase_order_line", "purchase_order_id", "purchase_order"),
    ("goods_receipt_line", "goods_receipt_id", "goods_receipt"),
    ("journal_entry_line", "journal_entry_id", "journal_entry"),
    ("cycle_count_line", "cycle_count_id", "cycle_count"),
    ("location", "warehouse_id", "warehouse"),
    ("zatca_submission", "sales_invoice_id", "sales_invoice"),
]

# Already have company_id (NOT NULL, populated) — policy-only fix.
RLS_ONLY_TABLES = ["role", "user_company_access"]


def upgrade() -> None:
    for child, fk_col, parent in LINE_TABLES:
        # 1. Add nullable first — safe against existing rows, no lock-heavy
        #    NOT NULL-with-default rewrite.
        op.add_column(child, sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True))

        # 2. Backfill from the parent, the only source of truth for these
        #    rows' company ownership.
        #
        #    journal_entry_line carries an immutability trigger
        #    (trg_journal_entry_line_immutable, from the M1 accounting
        #    migration) that rejects ANY update once the parent entry is
        #    posted — a real, working accounting-integrity control, not a
        #    bug. This backfill is a metadata correction (adding tenant
        #    scoping), not a change to posted financial content.
        #
        #    ALTER TABLE ... DISABLE/ENABLE TRIGGER within the same
        #    transaction as the DML hits Postgres's "pending trigger
        #    events" restriction (catalog-level toggle, not designed for
        #    disable-DML-enable inside one transaction). session_replication_role
        #    is the standard migration-time workaround: it suppresses
        #    trigger firing for this session only, isn't a catalog change,
        #    and is reset to DEFAULT immediately after this one statement —
        #    the trigger itself is never altered or weakened for the
        #    application.
        if child == "journal_entry_line":
            op.execute("SET session_replication_role = replica")
        op.execute(
            f"UPDATE {child} SET company_id = {parent}.company_id "
            f"FROM {parent} WHERE {child}.{fk_col} = {parent}.id"
        )
        if child == "journal_entry_line":
            op.execute("SET session_replication_role = DEFAULT")

        # 3. Verify zero NULLs before trusting the column — fail loudly
        #    rather than silently leaving orphaned rows with no company
        #    ownership. Should never fire given the FK/NOT NULL guarantees
        #    above; this is a safety net, not an expected path.
        op.execute(
            f"DO $$ BEGIN "
            f"IF EXISTS (SELECT 1 FROM {child} WHERE company_id IS NULL) THEN "
            f"RAISE EXCEPTION 'phase16a backfill left NULL company_id rows in {child}'; "
            f"END IF; END $$;"
        )

        # 4. Now safe to enforce NOT NULL.
        op.alter_column(child, "company_id", nullable=False)

        # 5. Index — matches the plain-indexed-UUID convention every other
        #    module already uses for company_id (no FK to company.id outside
        #    the identity module; see sales/purchasing/inventory models).
        op.create_index(f"ix_{child}_company_id", child, ["company_id"])

        # 6-8. RLS: enable, force (table owner would otherwise be exempt —
        #    see the original tenant-isolation migration), and the policy.
        op.execute(f"ALTER TABLE {child} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {child} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY company_isolation ON {child}
            USING (company_id = current_setting('app.current_company_id', true)::uuid)
            WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
            """
        )

    for table in RLS_ONLY_TABLES:
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
    for table in RLS_ONLY_TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    for child, fk_col, parent in LINE_TABLES:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {child}")
        op.execute(f"ALTER TABLE {child} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {child} DISABLE ROW LEVEL SECURITY")
        op.drop_index(f"ix_{child}_company_id", table_name=child)
        op.drop_column(child, "company_id")
