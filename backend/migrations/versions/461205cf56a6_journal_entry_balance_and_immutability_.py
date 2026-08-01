"""journal entry balance and immutability triggers

Revision ID: 461205cf56a6
Revises: e5a4af408356
Create Date: 2026-07-31 19:13:28.341776
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '461205cf56a6'
down_revision: Union[str, None] = 'e5a4af408356'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FR-ACC-003 backstop (Phase 7 §1.6): the application layer already
    # rejects unbalanced entries before they're ever sent to the DB, but this
    # deferred constraint trigger is the last line of defense — it fires once
    # per COMMIT (not per row), after all of an entry's lines have been
    # inserted in the same transaction, so a multi-line INSERT is checked as
    # a whole rather than rejected mid-insert.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_check_journal_balanced() RETURNS TRIGGER AS $$
        DECLARE
            total_debit NUMERIC(18,4);
            total_credit NUMERIC(18,4);
            target_entry_id UUID;
        BEGIN
            target_entry_id := COALESCE(NEW.journal_entry_id, OLD.journal_entry_id);
            SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0)
              INTO total_debit, total_credit
              FROM journal_entry_line WHERE journal_entry_id = target_entry_id;
            IF total_debit <> total_credit THEN
                RAISE EXCEPTION 'Journal entry % is not balanced: debit=%, credit=%',
                    target_entry_id, total_debit, total_credit;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_journal_entry_line_balanced
        AFTER INSERT OR UPDATE ON journal_entry_line
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION fn_check_journal_balanced()
        """
    )

    # FR-ACC-004: a Posted entry is immutable; only its status may move to
    # 'reversed' (Phase 5 business flow: correction happens via UC-ACC
    # reversal, never an edit).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_journal_entry_posted_immutable() RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.status = 'posted' THEN
                IF NEW.status NOT IN ('posted', 'reversed') THEN
                    RAISE EXCEPTION 'Cannot change status of a posted journal entry to %', NEW.status;
                END IF;
                IF NEW.entry_date <> OLD.entry_date
                   OR NEW.journal_id <> OLD.journal_id
                   OR NEW.company_id <> OLD.company_id THEN
                    RAISE EXCEPTION 'Cannot modify a posted journal entry; create a reversal instead';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_journal_entry_posted_immutable
        BEFORE UPDATE ON journal_entry
        FOR EACH ROW EXECUTE FUNCTION fn_journal_entry_posted_immutable()
        """
    )

    # Lines of a posted entry cannot be changed or removed either.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_journal_entry_line_immutable() RETURNS TRIGGER AS $$
        DECLARE
            parent_status TEXT;
        BEGIN
            SELECT status INTO parent_status FROM journal_entry WHERE id = OLD.journal_entry_id;
            IF parent_status = 'posted' THEN
                RAISE EXCEPTION 'Cannot modify lines of a posted journal entry';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_journal_entry_line_immutable
        BEFORE UPDATE OR DELETE ON journal_entry_line
        FOR EACH ROW EXECUTE FUNCTION fn_journal_entry_line_immutable()
        """
    )

    # Phase 7 §1.4: belt-and-suspenders tenant isolation for company-scoped
    # accounting tables (these carry company_id, not tenant_id — see Phase 7 §3).
    for table in ["account", "journal", "cost_center", "tax_group", "tax_rate", "fiscal_period", "journal_entry"]:
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
    for table in ["account", "journal", "cost_center", "tax_group", "tax_rate", "fiscal_period", "journal_entry"]:
        op.execute(f"DROP POLICY IF EXISTS company_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP TRIGGER IF EXISTS trg_journal_entry_line_immutable ON journal_entry_line")
    op.execute("DROP FUNCTION IF EXISTS fn_journal_entry_line_immutable")
    op.execute("DROP TRIGGER IF EXISTS trg_journal_entry_posted_immutable ON journal_entry")
    op.execute("DROP FUNCTION IF EXISTS fn_journal_entry_posted_immutable")
    op.execute("DROP TRIGGER IF EXISTS trg_journal_entry_line_balanced ON journal_entry_line")
    op.execute("DROP FUNCTION IF EXISTS fn_check_journal_balanced")
