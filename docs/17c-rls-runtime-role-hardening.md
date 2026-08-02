# Phase 17C-RLS — Database Runtime Role Hardening

## 1. Why this phase exists

Every RLS policy in this project (`tenant_isolation`, `company_isolation`,
and now `*_login_lookup`) was, for the project's entire history until this
phase, evaluated by a Postgres connection authenticated as `erp` — the
official `postgres` Docker image's mandatory bootstrap role. Docker's
image always makes `POSTGRES_USER` a full superuser at `initdb` time; there
is no supported way to make it anything else. A Postgres superuser (and
any `BYPASSRLS` role) bypasses Row-Level Security **unconditionally**,
regardless of `FORCE ROW LEVEL SECURITY` or the policy's `USING`/`WITH
CHECK` clauses. Every `pg_policies` row in this database was real, but none
of them had ever actually been enforced for the application's own traffic —
only proven in isolated, disposable-role experiments.

This phase closes that gap: it introduces two new, genuinely restricted
roles, moves the API and Celery worker onto one of them, and — because
doing so immediately surfaced several latent bugs that only a real
non-bypassing role could expose — fixes each one.

## 2. Role architecture

| Role | Login | Superuser | Bypass RLS | Create DB/Role | Owns tables | Used by |
|---|---|---|---|---|---|---|
| `erp` (bootstrap) | yes | **yes** (Docker-mandated) | yes | yes | no (after bootstrap) | Nothing, after the one-off bootstrap step. Never referenced by `api`/`worker`/Alembic config. |
| `erp_migrate` | yes | no | no | no | **yes** (all 46 tables) | Alembic only, via the one-off `migrate` compose service. |
| `erp_app` | yes | no | no | no | no | `api` and `worker` — 100% of runtime traffic. |

`erp_app`'s grants are the minimum the application actually needs:
`USAGE` on schema `public`, `SELECT`/`INSERT`/`UPDATE`/`DELETE` on every
table. Explicitly **not** granted: `TRUNCATE`, `REFERENCES`, `TRIGGER`,
`CREATE`, `ALTER`/`DROP` (no DDL at all), table ownership, `CREATEROLE`,
`CREATEDB`. `ALTER DEFAULT PRIVILEGES FOR ROLE erp_migrate IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO erp_app` means every
*future* table Alembic creates (as `erp_migrate`, the schema owner)
automatically grants `erp_app` the same rights — no migration ever needs
to remember a manual grant step again.

## 3. Bootstrap: `backend/src/scripts/bootstrap_db_roles.py`

Idempotent, safe to re-run any number of times, against a genuinely fresh
database or an already-populated one (including this project's own
long-lived dev database, upgraded in place). Run via the `migrate` compose
service, connected with the bootstrap `erp` credential
(`DATABASE_URL_BOOTSTRAP_SYNC` in `.env.migrate`/`.env.migrate.production`
— the only place that credential is ever used):

1. Creates (or re-asserts the password/attributes of) `erp_migrate` and
   `erp_app`.
2. Grants `erp_migrate` `USAGE`+`CREATE` on schema `public` and `CREATE` on
   the database itself (needed for `CREATE EXTENSION pgcrypto` — confirmed
   during Step 2's experiment to be a *trusted* extension on this Postgres
   16 image, so this doesn't require superuser).
3. If the bootstrap role currently owns any tables (true the first time
   this runs against an existing database; a no-op — "reassigned 0
   table(s)" — on a fresh one), reassigns them to `erp_migrate` via a
   **targeted per-table `ALTER TABLE ... OWNER TO`**, not a blanket
   `REASSIGN OWNED BY`. The blanket form fails
   (`DependentObjectsStillExist`) because the bootstrap role also owns the
   *database* itself, which Postgres refuses to reassign as a side effect.
4. Grants `erp_app` its runtime privileges (see §2) on every table that
   exists right now, and sets the `ALTER DEFAULT PRIVILEGES` rule so this
   never needs to happen again for tables created after this point.

No password is ever hardcoded in the script or logged — all four required
values come from the environment.

## 4. Credential separation: which `.env` file each service loads

| Compose service | `.env` file | Role | Purpose |
|---|---|---|---|
| `migrate` (dev) | `backend/.env.migrate` | `erp` (bootstrap) → creates `erp_migrate`/`erp_app` → Alembic runs as `erp_migrate` | One-off, `profiles: ["tools"]`, not part of `up` |
| `migrate` (prod) | `backend/.env.migrate.production` | same | same |
| `api` (dev) | `backend/.env` | `erp_app` | Every HTTP request |
| `api` (prod) | `backend/.env.production` | `erp_app` | Every HTTP request |
| `worker` | same as `api` | `erp_app` | Every Celery task |

`migrations/env.py` resolves its connection URL as
`settings.database_url_migrate_sync or settings.database_url_sync` — an
explicit, documented fallback (not a silent one): a developer's plain
`.env` with no separate migrate role configured yet still works by falling
back to whatever `database_url_sync` is, but production's `.env.migrate*`
must always set `DATABASE_URL_MIGRATE_SYNC` explicitly.

Startup ordering in both compose files: `postgres` (healthy) → `migrate`
(one-off, must complete before the next step) → `api`/`worker`. No
circular dependencies; `api`/`worker` never depend on `migrate` at the
compose level (it's not part of `up` at all), but the *data* they depend on
(roles existing, schema at head) does.

## 5. The `session_replication_role` guard (historical migration only)

One historical migration, `8957d3c39d54` (Phase 16A), used `SET
session_replication_role = replica` to suppress trigger firing during a
one-time metadata backfill. That statement requires genuine Postgres
superuser (`PGC_SUSET` GUC context) — no grant can change that. Guarded:

```python
if child == "journal_entry_line":
    is_superuser = bind.execute(
        sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    if is_superuser:
        op.execute("SET session_replication_role = replica")
```

**Empirically proven safe for fresh installs** (Step 2's disposable-database
experiment, reconfirmed by this phase's own fresh-DB test in §9): on a
fresh database the table this backfill targets is empty, so the trigger
this statement suppresses has nothing to fire on — the guard's `false`
branch and the unguarded original produce byte-for-byte identical
resulting schema/data/RLS state. **Accepted limitation**: restoring a
*historical, pre-16A* database dump under `erp_migrate` (non-superuser)
would still fail at this one step, because that scenario genuinely needs
the trigger-suppression behavior against non-empty legacy data. No standing
superuser migration credential was introduced to cover this — it's
accepted as a known, narrow, documented gap rather than reintroducing a
permanent privilege escalation for a scenario this project has never
actually needed.

## 6. ZATCA worker ordering fix

`report_invoice_task` (`src/workers/tasks/zatca_tasks.py`) used to look up
the invoice with `invoice_repo.get_by_id()` *before* calling
`set_company_context()`. Invisible under the superuser role; under
`erp_app`, that lookup runs under `company_isolation`'s default-deny with
no context set — silently returning nothing, every time, so invoices were
never reported. `SalesInvoice` and `Company` are looked up under two
*different* RLS families (`company_isolation` and `tenant_isolation`
respectively — see Phase 7 §3), so the fix threads **both** `company_id`
and `tenant_id` from the enqueue-time `AuthContext` through `.delay()` →
`report_invoice_task` → `_run_with_fresh_pool` → `_report_invoice_async`,
setting both contexts before the first query. Both `.delay()` sites
(`issue_invoice`, `issue_credit_note` in `sales/api/routes.py`) pass them.

Backward-compatible: both new parameters are optional
(`company_id: str | None = None`, `tenant_id: str | None = None`), so an
old-shape task already in Redis at deploy time doesn't crash — its
first-query lookup fails closed (no context → no rows → early return,
idempotent no-op) rather than raising. No standing superuser/bypass
workaround. Operationally, draining the ZATCA queue before deploying this
change avoids that scenario entirely; the fallback exists as a safety net,
not the primary plan.

## 6a. Identity bootstrap couldn't create a company either

The same category of bug, found independently while first switching `api`
to `erp_app`: `POST /identity/bootstrap` (the one unauthenticated
tenant/company-creation endpoint) called `set_tenant_context()` but never
`set_company_context()`. `role` and `user_company_access` carry
`company_isolation` RLS (Phase 16A) — tenant context alone doesn't satisfy
their `WITH CHECK` clause, so creating the bootstrap admin's role and
company-access grant failed under real enforcement. Fixed by calling
`set_company_context(db, company.id)` in `identity/api/routes.py`'s
`bootstrap()` handler right after the company is registered, before the
admin user/role/`user_company_access` rows are created — no RLS policy
change, just establishing context that was silently assumed unnecessary
while the superuser bypassed it.

## 7. Step 3A: login/2FA couldn't authenticate at all

Verifying the fix above end-to-end (§10's integration tests) surfaced a
second, independent, and more serious gap: `app_user` has carried
`tenant_isolation` RLS with `FORCE ROW LEVEL SECURITY` since the very first
RLS migration (`42bc09c34924`). The unauthenticated login/2FA-verify flow
looks a user up **by email alone**, before any tenant is known — that's
the entire point of email/password login. Under real enforcement, that
lookup can never return a row, for anyone, ever:

```sql
-- fresh erp_app session, app.current_tenant_id never set
SELECT count(*) FROM app_user;  →  0
```

Already-authenticated requests were never affected —
`get_auth_context()` sets tenant/company context from the JWT's own claims
before touching the database — but nobody could obtain a session at all.

**Fix (migrations `f7004fe055a4`, `0fc571b91522`)**: two new, additive,
`SELECT`-only RLS policies, gated by a transaction-local
`app.login_lookup` flag:

```sql
CREATE POLICY app_user_login_lookup ON app_user
FOR SELECT USING (current_setting('app.login_lookup', true) = 'true');

CREATE POLICY user_company_access_login_lookup ON user_company_access
FOR SELECT USING (current_setting('app.login_lookup', true) = 'true');
```

Postgres OR's permissive policies together per command — the existing
`tenant_isolation`/`company_isolation` policies (`cmd = ALL`) are
untouched, byte-for-byte, and remain the *only* policy governing
INSERT/UPDATE/DELETE on both tables. `user_company_access` needed the same
treatment because `AuthenticationService.issue_tokens()` calls
`list_authorized_companies()` immediately after a successful login — same
"context not known yet" problem, same fix, same flag.

`set_login_lookup()` (`src/shared/infrastructure/db/session.py`) is the
only place `app.login_lookup` is ever set, called only from the
`login`/`verify_2fa` route handlers, never from a general-purpose
repository method:

```python
await session.execute(text("SET LOCAL app.login_lookup = 'true'"))
await session.execute(text(f"SET LOCAL app.current_tenant_id = '{_NIL_UUID}'"))
await session.execute(text(f"SET LOCAL app.current_company_id = '{_NIL_UUID}'"))
```

The nil-UUID sentinel lines are not an RLS decision — the two policies
above are what actually grant access, through the flag alone. They're a
**connection-pool safety fix**, and they were empirically necessary:
Postgres creates a persistent per-connection placeholder the first time a
custom GUC name is referenced (e.g. by any prior authenticated request on
this same pooled connection calling `set_tenant_context`). Once that
placeholder exists, ending that transaction resets the GUC to an **empty
string**, not back to `NULL`, for the rest of that physical connection's
life. `tenant_isolation`'s `current_setting(...)::uuid` cast raises a hard
error on `''` — and since Postgres OR's permissive policies together, that
raises *before* `app_user_login_lookup`'s own clause is even reached,
crashing login on any previously-used pooled connection regardless of the
new policy's correctness. Setting a syntactically valid (nil) UUID
sentinel avoids the cast error without touching `tenant_isolation` at all;
the sentinel can never match a real tenant/company, so it never grants
anything by itself. Verified directly:

```python
# on a connection deliberately tainted by an earlier SET LOCAL + rollback
await conn.execute(text("SET LOCAL app.login_lookup = 'true'"))
await conn.execute(text("SET LOCAL app.current_tenant_id = '00000000-0000-0000-0000-000000000000'"))
# SELECT count(*) FROM app_user  →  1526 (real rows, no crash)
```

## 8. A third instance of the same bug class: cycle-count endpoints

Running the full backend suite after the login fix surfaced a third,
unrelated case: `POST /inventory/cycle-counts` and
`POST /inventory/cycle-counts/{id}:approve` both call `await db.commit()`
and then run a further RLS-protected query
(`cycle_count_repo.get_lines(...)`) on the same session. `SET LOCAL` is
transaction-scoped — it doesn't survive the commit — so the follow-up read
hit the identical tainted-connection `''`-cast crash described in §7. A
full audit of every `commit()` call site across all 6 route modules (32
total) found this pattern in exactly these two handlers, nowhere else.
Fixed by re-calling `set_company_context()` immediately after each
`commit()`, before the follow-up query — same pattern as everywhere else
in this phase, no new mechanism, no RLS policy involved.

## 9. Verification performed

- **Fresh database**: disposable container, `bootstrap_db_roles.py` then
  `alembic upgrade head` from empty, as `erp_migrate` (non-superuser),
  through the *actual* repository migrations (not a scratch copy) —
  reached head `0fc571b91522`. Confirmed: both roles `rolsuper=false,
  rolbypassrls=false, rolcreatedb=false, rolcreaterole=false`; all 46
  tables owned by `erp_migrate`; `app_user` still `FORCE ROW LEVEL
  SECURITY`; original `tenant_isolation` policy present and unchanged
  (`cmd=ALL`); both new `*_login_lookup` policies present (`cmd=SELECT`).
- **Existing database** (this project's real dev DB): bootstrap +
  migration run twice (idempotency check — second run: "reasserted role
  ...", "reassigned 0 table(s)", Alembic reports nothing pending) with no
  data loss; confirmed head matches the fresh-DB result exactly.
- **Direct RLS suite** (`tests/test_rls_enforcement.py`): 24/24 passing —
  18 tests across `product`, `product_category`, `unit_of_measure`,
  `journal_entry_line`, `company` (own/cross-company SELECT/UPDATE/DELETE/
  INSERT, bare SELECT, missing-context default-deny), plus 6 new tests for
  the login-lookup policies (missing context, enabled, SELECT-only,
  no unrelated-table bypass, ordinary tenant isolation unaffected,
  no leakage across transactions) — all against the real `erp_app` role.
- **ZATCA regression** (`tests/test_zatca_worker_context_ordering.py`):
  2/2 — proves the old call shape fails closed under real RLS and the
  fixed shape succeeds, using the real worker entry point.
- **Login/2FA integration** (`tests/test_login_lookup_integration.py`):
  4/4 — real HTTP bootstrap → login → authenticated call, wrong-password
  rejection, and a genuine end-to-end 2FA verification (real `pyotp` code
  against the real `verify-2fa` endpoint).
- **Full backend suite**: 130/130 passing, confirmed deterministic across
  three consecutive runs including a full Docker cold restart.
- **Frontend**: `tsc --noEmit` clean, `eslint` clean, `next build`
  succeeds (all 24 routes, unchanged from Phase 17B — this phase touched
  no frontend code).
- **Cold restart**: `docker compose down` (containers only, volume
  preserved) → `up postgres redis` → `migrate` → `up api worker` →
  `/health` returns `{"status":"ok","database":true}`; both `api` and
  `worker` confirmed connecting as `erp_app`.
- **Repository grep**: no reference to the bootstrap `erp` role's
  credentials outside `.env.migrate*` files.

## 10. Known limitations

- The historical-restore limitation in §5 (restoring a genuine pre-16A
  database dump would need a one-time superuser credential; not
  provisioned as a standing capability).
- The cross-tenant "sweep for invoices that never got enqueued at all"
  follow-up job noted in `zatca_tasks.py`'s module docstring (needs a
  `BYPASSRLS`-capable worker role to safely scan every company's
  `pending_submission` rows) remains explicitly out of scope — real infra
  work deferred, not bolted on here.
