"""Company login code

Hardening Issue #4 (Owner directive, 2026-08-18): "just email + password
isn't enough discipline for a remote client logging into their company —
they should also have to type a company code, so there's no mix-up." The
`app_user.email` unique index already makes cross-tenant identity mixing
technically impossible, but the code still adds real value: a defense-in-
depth login gate that confirms intent and catches typos/misdirected
credentials before a session is issued.

System-assigned (never user-typed, mirroring the existing product SKU /
partner code precedent), but globally unique across the whole `company`
table rather than per-company — `company` IS the tenant boundary, and the
code must be resolvable at login before any tenant context exists (same
shape as `app_user.email`). A 6-char uppercase-hex code (`gen_random_uuid`
is already relied on elsewhere in this schema, confirming pgcrypto is
available) keeps it short enough to type and read over a phone call while
avoiding ambiguous characters (hex has no I/L/O, so every character is
visually distinct from every other).

Revision ID: 5461ff610806
Revises: b2c3d4e5f6a7
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5461ff610806"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("company", sa.Column("code", sa.String(length=6), nullable=True))

    # `company` has FORCE ROW LEVEL SECURITY on `tenant_isolation` -- same
    # NO FORCE/FORCE bracket the partner_code/account precedents use for
    # this exact situation (a bulk cross-tenant backfill with no
    # app.current_tenant_id set yet, which the policy's cast would either
    # reject or -- as confirmed live here -- silently filter to zero rows).
    op.execute("ALTER TABLE company NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        UPDATE company
        SET code = upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 6))
        """
    )
    # This dev database carries ~40k accumulated test-run company rows (a
    # side effect of a very long session's worth of pytest bootstrap()
    # calls, not representative of real usage) -- at that row count, a
    # single random-generation pass over a 6-hex-char space (16.7M) hits
    # the birthday paradox and reliably produces duplicates. Self-heals by
    # re-rolling just the colliding rows and re-checking until clean,
    # rather than widening the code (which would make it needlessly long
    # for the real target: a handful of companies per real tenant).
    op.execute(
        """
        DO $$
        DECLARE
            dup_count integer;
        BEGIN
            LOOP
                UPDATE company c
                SET code = upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 6))
                FROM (
                    SELECT code FROM company GROUP BY code HAVING count(*) > 1
                ) dups
                WHERE c.code = dups.code;
                GET DIAGNOSTICS dup_count = ROW_COUNT;
                EXIT WHEN dup_count = 0;
            END LOOP;
        END $$;
        """
    )
    op.execute("ALTER TABLE company FORCE ROW LEVEL SECURITY")

    op.alter_column("company", "code", nullable=False)
    op.create_index(
        "ux_company_code",
        "company",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_company_code", table_name="company")
    op.drop_column("company", "code")
