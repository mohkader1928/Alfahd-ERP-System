"""Phase 17C-RLS: idempotent bootstrap for the erp_migrate / erp_app roles.

Run once (safe to re-run any number of times, including against this
project's already-populated development database) BEFORE
`alembic upgrade head`, connected using the PostgreSQL *bootstrap*
superuser credentials — whatever role the official `postgres` Docker image
made a superuser at container init (`POSTGRES_USER`). That bootstrap role
is never used by API, worker, or Alembic after this script runs; only this
one-off setup step touches it.

What this does, in order — every step is idempotent, so re-running is safe:

  1. Creates `erp_migrate` and `erp_app` if they don't already exist
     (LOGIN, NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE for both —
     see docs/17c-rls-runtime-role-hardening.md for why). If they already
     exist, their password/attributes are reasserted to match the current
     environment rather than skipped, so rotating a password just means
     re-running this script.
  2. Grants `erp_migrate` what it needs to create and own schema objects:
     `USAGE`+`CREATE` on the target schema, and `CREATE` on the database
     itself (needed for `CREATE EXTENSION pgcrypto` — a *trusted* extension,
     verified directly against this project's Postgres 16 image in Phase
     17C-RLS Step 1, so this does not require superuser).
  3. If the bootstrap role currently owns any objects (this project's
     existing development database, or any already-deployed database being
     upgraded to this architecture for the first time), reassigns that
     ownership to `erp_migrate` via `REASSIGN OWNED BY` — a no-op on a
     fresh database where the bootstrap role owns nothing yet.
  4. Grants `erp_app` `USAGE` on the schema, and `SELECT`/`INSERT`/
     `UPDATE`/`DELETE` on every table that currently exists — a no-op on a
     fresh database (there are none yet); the real effect on an existing
     database being upgraded.
  5. Sets `ALTER DEFAULT PRIVILEGES` so every table `erp_migrate` creates
     from this point on (every future Alembic migration) automatically
     grants `erp_app` the same DML rights, with no further manual grant
     step ever required again.

Required environment variables:
  DATABASE_URL_BOOTSTRAP_SYNC   plain `postgresql://user:pass@host:port/db`
                                 URI using the bootstrap role's credentials
                                 (NOT the `postgresql+psycopg2://` SQLAlchemy
                                 form used elsewhere in this project — this
                                 script talks to psycopg2 directly)
  POSTGRES_DB                   the target database name
  ERP_MIGRATE_PASSWORD          password to (re)assert for erp_migrate
  ERP_APP_PASSWORD              password to (re)assert for erp_app

No password is ever hardcoded here or logged — all four come from the
environment, matching this project's existing `DATABASE_URL`-from-env
convention.
"""

import os
import sys

import psycopg2
from psycopg2 import sql

ERP_MIGRATE_ROLE = "erp_migrate"
ERP_APP_ROLE = "erp_app"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required to run this script")
    return value


def _bootstrap_dsn() -> str:
    # Accept either form so a copy-pasted SQLAlchemy-style URL doesn't
    # silently fail — psycopg2.connect() only understands the plain form.
    return _required_env("DATABASE_URL_BOOTSTRAP_SYNC").replace("postgresql+psycopg2://", "postgresql://")


def _ensure_role(cur, role: str, password: str) -> None:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
    exists = cur.fetchone() is not None
    verb = "ALTER ROLE" if exists else "CREATE ROLE"
    login_clause = "LOGIN" if not exists else "WITH LOGIN"
    cur.execute(
        sql.SQL(f"{verb} {{}} {login_clause} PASSWORD %s NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE").format(
            sql.Identifier(role)
        ),
        (password,),
    )
    print(f"{'reasserted' if exists else 'created'} role {role}")


def main() -> None:
    db_name = _required_env("POSTGRES_DB")
    migrate_password = _required_env("ERP_MIGRATE_PASSWORD")
    app_password = _required_env("ERP_APP_PASSWORD")

    conn = psycopg2.connect(_bootstrap_dsn())
    conn.autocommit = True
    try:
        bootstrap_role = conn.info.user
        with conn.cursor() as cur:
            _ensure_role(cur, ERP_MIGRATE_ROLE, migrate_password)
            _ensure_role(cur, ERP_APP_ROLE, app_password)

            cur.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(sql.Identifier(ERP_MIGRATE_ROLE)))
            cur.execute(
                sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                    sql.Identifier(db_name), sql.Identifier(ERP_MIGRATE_ROLE)
                )
            )
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ERP_APP_ROLE)))

            if bootstrap_role != ERP_MIGRATE_ROLE:
                # Targeted per-table ownership transfer rather than a
                # blanket `REASSIGN OWNED BY` — the bootstrap role also
                # owns the database itself (and other objects Postgres
                # considers "required by the database system"), and a
                # blanket REASSIGN errors out trying to touch those. Tables
                # are the only object type this project actually has
                # (confirmed: zero sequences, no bootstrap-role-owned
                # functions/triggers — those are owned by whoever creates
                # them via CREATE FUNCTION, i.e. erp_migrate once it starts
                # running migrations, never the bootstrap role).
                cur.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tableowner = %s",
                    (bootstrap_role,),
                )
                bootstrap_owned_tables = [row[0] for row in cur.fetchall()]
                for table in bootstrap_owned_tables:
                    cur.execute(
                        sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                            sql.Identifier(table), sql.Identifier(ERP_MIGRATE_ROLE)
                        )
                    )
                print(
                    f"reassigned {len(bootstrap_owned_tables)} table(s) owned by {bootstrap_role} "
                    f"to {ERP_MIGRATE_ROLE} (0 is expected/correct on a fresh database)"
                )

            cur.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(
                    sql.Identifier(ERP_APP_ROLE)
                )
            )
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(sql.Identifier(ERP_MIGRATE_ROLE), sql.Identifier(ERP_APP_ROLE))
            )
        print("bootstrap complete", file=sys.stderr)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
