# Developer Guide — Saudi ERP System

**Phase-One v1.0.0.** This is the developer onboarding index: it documents the actual system as it exists in this repository today, and points to the authoritative existing docs rather than duplicating them. Nothing below describes planned or aspirational architecture — every claim is grounded in a specific file in this repo. Where an existing doc is known to be stale, that's called out explicitly rather than silently trusted.

---

## 1. Architecture overview

Modular monolith: one FastAPI backend, one Next.js frontend, one PostgreSQL database with Row-Level Security (RLS) as the tenant-isolation boundary. Full architectural rationale is in [`08-system-architecture.md`](08-system-architecture.md) — read that first. This guide assumes it and focuses on what's changed or under-documented since.

## 2. Module boundaries (backend)

`backend/src/modules/` — one directory per business domain: `accounting`, `attachments`, `fixed_assets`, `identity`, `inventory`, `notifications`, `payments`, `purchasing`, `reporting`, `sales`, `zatca`. Each module follows the same internal layout (`api/`, `application/`, `domain/`, `infrastructure/`) described in [`09-folder-structure.md`](09-folder-structure.md). `identity` is the exception worth knowing up front: it owns not just users/roles but also company/branch/tenant, partners, products, and the audit log — it's the module every other module depends on, not a peer.

`backend/src/shared/` holds cross-module infrastructure: `security/` (JWT, password hashing/policy, TOTP, auth context), `email/` (mailer), `infrastructure/db/` (session factory, RLS context setters), `idempotency/`, `media/`, `reporting/` (export rendering, formatting, labels), `i18n/`.

## 3. Frontend structure

Next.js App Router. `frontend/app/(auth)/` — unauthenticated pages (login, forgot-password, reset-password, setup, select-company). `frontend/app/(dashboard)/` — everything behind auth, one directory per business area, mirroring the backend module split closely but not exactly (e.g. `fixed-assets` has five separate pages under one nav group; `accounting` is one page with tab-based routing via `?tab=`). `frontend/lib/nav-config.ts` is the single source of truth for the sidebar — every `href` there resolves to a real page; the file's own comment explains why fake nav entries are prohibited. `frontend/lib/i18n/` — `ar.json`/`en.json`, loaded via `useI18n()`.

## 4. Database & migrations

Alembic, `backend/migrations/versions/`. **Read the revision graph before writing a new migration** — this project has had at least one real revision-ID collision (two unrelated migrations independently picked the same 12-hex-char ID; see `a8b9c0d1e2f3_password_reset_and_login_lockout.py`'s history for the exact incident). Before creating a migration, grep the existing filenames for your intended revision ID:

```bash
grep -rn "^revision" backend/migrations/versions/*.py
```

Migrations run under a schema-owning role (`erp_migrate`), not the runtime app role (`erp_app`) — see §6. Apply locally via the `migrate` compose profile, never by pointing the api/worker containers' own `DATABASE_URL` at a migration:

```bash
docker compose -f infra/docker-compose.yml --profile tools run --rm migrate python -m alembic upgrade head
```

## 5. RLS & multi-tenancy model

Full design rationale: [`16-multi-tenancy-hardening.md`](16-multi-tenancy-hardening.md) and [`17c-rls-runtime-role-hardening.md`](17c-rls-runtime-role-hardening.md). The short version every new route/service needs:

- Every tenant-scoped table has a `tenant_isolation` (or `company_isolation`) RLS policy keyed off `current_setting('app.current_tenant_id')`/`app.current_company_id`, cast to `uuid`.
- `set_tenant_context(session, tenant_id)` / `set_company_context(session, company_id)` (`shared/infrastructure/db/session.py`) set these via `SET LOCAL` — transaction-scoped, never leak across pooled connections.
- **Pre-authentication code paths** (login, refresh, password reset) can't call those normally — no tenant is known yet. They use `set_login_lookup(session)` instead, which flips a narrow, additive, SELECT-only escape-hatch policy and resets both GUCs to a nil-UUID sentinel. Read that function's docstring in full before touching any of `/auth/*` — it explains a genuinely non-obvious connection-pool GUC-reset gotcha (ending a transaction resets a custom GUC to `''`, not `NULL`, once any connection in the pool has ever set it — `''::uuid` then hard-fails the cast, which is why the nil-UUID sentinel exists at all).
- **Commit ordering matters** when a route both mutates RLS-relevant state and needs a `set_login_lookup`-gated read afterward in the same request. `/auth/login` is the concrete example: committing between `authenticate_step1()` (which may write `failed_login_count`) and `issue_tokens()` (which reads `user_company_access` under the login-lookup escape hatch) silently breaks the second read, because committing ends the transaction the escape hatch was scoped to. The fix (see `identity/api/routes.py`) is to defer the commit until *after* `issue_tokens()` returns, not before. Any future route with the same shape (mutate pre-auth state, then read something else pre-auth-gated) needs the same ordering.

## 6. Authentication & session model

- `AuthenticationService` (`identity/application/services.py`) — `authenticate_step1`/`authenticate_step2_totp`, `issue_tokens`, `refresh_tokens`. JWT access tokens (30 min) carry `authorized_companies`; refresh tokens (7 days) rotate on use.
- **Password reset** (`PasswordResetService`, same file): request/confirm flow, `password_reset_token` table (deliberately no RLS/`company_id` — same pre-auth shape as `app_user`'s own login-lookup problem). Anti-enumeration by design: `request_reset` always returns the same response and never reveals whether the email exists.
- **Login lockout**: `AuthenticationService.MAX_FAILED_LOGIN_ATTEMPTS` (5) / `LOCKOUT_DURATION_MINUTES` (15), backed by `app_user.failed_login_count`/`locked_until`. Auto-expiring by design — never a permanent lock. A successful password reset also clears it, so it's the account-recovery path too.
- **2FA**: TOTP, `shared/security/totp.py`. Enrollment (`start_2fa_enrollment`/`verify_2fa_enrollment`) is separate from the login challenge (`authenticate_step2_totp`).

## 7. Authorization / RBAC

`require_permission(code, require_branch=False)` (`identity/api/deps.py`) is the standard route dependency. Permission codes are checked against `role_permission` via `RoleRepository.get_user_permission_codes`. System roles (created at bootstrap) are immutable by `is_system` flag — permissions on them can be edited, the role itself can't be renamed/deleted.

## 8. API conventions

- Colon-suffixed action verbs for non-CRUD operations on a resource: `POST /orders/{id}:invoice`, `POST /journal-entries/{id}:cancel`, `POST /fixed-assets/{id}:dispose`. Grep any module's `routes.py` for `":..."` to see the pattern.
- Standard error mapping: domain `ValueError` → 422, `AuthenticationError`/similar → 401, not-found → 404, permission failure (via `require_permission`) → 403 (raised inside the dependency, before the route body runs).
- Idempotency-Key support (`shared/idempotency/`) is opt-in per-endpoint, used where a client retry of the same logical action must not double-post (see `sales/api/routes.py`'s credit-note endpoints for the reference implementation).

## 9. Audit trail conventions

Two tables exist under `identity/infrastructure/models.py`: `AuditLog` (field-diff shape: `target_table`/`target_id`/`field_name`/`old_value`/`new_value`, actor, `changed_at`) and `ActivityLog` (action-string shape). **Only `AuditLog` is wired up** — it has a repository (`AuditLogRepository`), a listing endpoint (`GET /identity/audit-log`, filterable by `target_table`), and real call sites (chart-of-accounts edits, journal-entry status transitions, role creation, and — as of Phase-One P0-C — sales invoice issuance, credit notes, FA depreciation runs, FA disposal). `ActivityLog` has zero call sites anywhere in the codebase; treat it as dead schema, not as a second audit system to extend. When adding a new audited action, reuse `AuditLogRepository(db).record(...)` with `old_value=None` for creation-style events (mirrors the existing chart-of-accounts-deletion and invoice-issuance call sites) — don't invent a new mechanism.

One operational gotcha found while adding the P0-C call sites: `AuditLogRepository.record()` does an explicit `session.flush()`, which flushes *every* pending change in the session, not just the new `AuditLog` row. If the same request already has an unflushed attribute change on another tracked object (e.g. a `Decimal` field just assigned from request input, not yet round-tripped through Postgres), that flush can resync it to the DB's actual column precision (e.g. a `NUMERIC(18,4)` column silently going from `"1300.00"` to `"1300.0000"` in the response). This isn't a bug in the audit call — it's the response becoming *more* consistent with what a fresh read of the same row would show — but it's a real, reproducible side effect worth knowing about before assuming an audit-log call is side-effect-free.

## 10. Testing

`backend/tests/`, `pytest` + `pytest-asyncio`, one file per feature area. `tests/conftest.py` provides the `client` fixture (ASGI transport against the real app) and `unique_email()`/`unique_vat()` helpers used throughout. Standard pattern: bootstrap a fresh tenant/company/admin per test via `POST /identity/bootstrap`, log in, exercise the endpoint(s), assert.

**Known gap:** [`11-testing.md`](11-testing.md) is stale — it predates most of the modules and P0-work described in this guide and in `project-progress.md`. Don't treat it as current; treat `backend/tests/*.py` themselves, and the commit history, as the source of truth for what's actually tested. Updating that doc is flagged in the Post-Phase-One backlog (§22).

Run the full suite:

```bash
docker exec erp-nucleus-api-1 python -m pytest
```

Run one file/test:

```bash
docker exec erp-nucleus-api-1 python -m pytest tests/test_login_lockout.py -v
```

Lint: `docker exec erp-nucleus-api-1 python -m ruff check src/`. Frontend: `npx tsc --noEmit` and `npx eslint <path>` from `frontend/`.

## 11. Local dev environment

`infra/docker-compose.yml` — services `postgres`, `redis`, `migrate` (tools profile, one-shot), `api`, `worker`. Backend/frontend source is volume-mounted, so edits take effect without a rebuild for interpreted changes; migrations still need an explicit `alembic upgrade head` run (§4).

## 12. Environment variables & secrets

`backend/.env` (dev) / `.env.production` for the api/worker services, using the `erp_app` runtime role. `backend/.env.migrate` (gitignored, copy from `.env.migrate.example`) for the one-off `migrate` service, using the schema-owning `erp_migrate` role. Never point api/worker at `erp_migrate` — see `17c-rls-runtime-role-hardening.md` for why the role split exists at all.

## 13. Deployment

[`14-deployment.md`](14-deployment.md) is the authoritative doc — production Dockerfiles, `docker-compose.prod.yml`, nginx reverse proxy, migration runbook. Not re-derived here.

## 14. ZATCA / VAT integration

`modules/zatca/` — hash-chain (`infrastructure/hash_chain.py`, `GENESIS_HASH`), clearance (tax invoices, synchronous) vs. reporting (simplified invoices, async via Celery — see §19) submission paths. Tax rates are configurable data (`accounting.tax_rate` table + `GET /accounting/tax-rates`), not a hardcoded percentage — every VAT calculation site in `sales`/`purchasing` resolves a real `tax_rate_id` per line.

## 15. Inventory valuation & concurrency

Moving-average costing. `StockQuant`/`Layer` model under `modules/inventory/`; concurrent stock mutations are serialized per-product-per-warehouse (see the inventory concurrency audit referenced in `project-progress.md`'s Phase 16B history) — don't remove the row-locking pattern in `inventory/application/services.py` without re-reading why it's there first.

## 16. Accounting / journal-entry lifecycle

`draft → posted`, with `cancel` (draft only) and `reverse` (posted only) as the two exit paths — see §8's routing convention and §9 for how each transition gets audit-logged. Fiscal-period closing (`fiscal_period` table) gates posting: a closed period rejects any new/edited entry dated inside it with a 409, handled by a global exception handler mapping `PeriodClosedError` (see `project-progress.md`'s P0-2 entry for the original implementation).

## 17. Background workers (Celery)

`backend/src/workers/celery_app.py` + `tasks/zatca_tasks.py` — currently the only task family is ZATCA reporting (`report_invoice_task`), enqueued *after* the enclosing transaction commits (never before — a worker picking up a row from an uncommitted transaction would see nothing). Redis is the broker (`redis` compose service).

## 18. Idempotency patterns

`shared/idempotency/` — `IdempotencyKeyRepository`, `begin_idempotent_request`/`IdempotentReplay`. Opt-in via an `Idempotency-Key` header; used where a genuine client retry (not a legitimate repeat business action) must replay the original response rather than re-execute. See §8 and `sales/api/routes.py`'s credit-note endpoints for the full pattern including the replay short-circuit.

## 19. i18n / RTL conventions

`frontend/lib/i18n/{ar,en}.json`, consumed via `useI18n()`'s `t()`. Arabic is the system default (`preferred_locale` defaults to `"ar"` on `AppUser`); the UI supports a live language toggle without reload. New user-facing strings need both keys added in the same change — a missing key falls back to the raw key string, which is a fast way to spot one that was forgotten.

## 20. Reporting conventions

`shared/reporting/` — `export_render.py`/`export_response.py` (PDF/Excel export, shared across every report screen), `formatting.py` (currency/date formatting), `labels.py` (report column labels). Trial Balance / Income Statement / Balance Sheet all accept a `detail_level` (1–4, matching the Chart of Accounts' 4-level hierarchy cap) to toggle summary vs. full detail — see `accounting/api/routes.py`.

## 21. Release / versioning conventions

Git tags mark completed milestones: `phase-one-pre-closure`, `phase-one-p0-1-vat-complete`, `phase-one-p0-2-period-closing-complete`, `phase-one-p0-3-2fa-complete`, and (this release) `phase-one-v1.0.0`. Commit messages follow a `<Area>: <what changed>` convention with the *why* in the body, not the subject line — read recent `git log` for the house style before writing one. One concern per commit; full regression + ruff/tsc/eslint before every commit that touches runtime code.

## 22. Post-Phase-One backlog (known, non-blocking)

Enhancements identified during Phase-One closure work that are real but deliberately **not** implemented now, per the explicit Phase-One scope rule (finish, don't expand):

- No frontend viewer for the audit log — `GET /identity/audit-log` exists and works, but nothing in `frontend/` calls it. A dedicated Settings screen would be the natural home.
- `ActivityLog` (§9) is dead schema — either wire it up for a real purpose or drop it in a future migration; don't leave it as an unused table indefinitely.
- [`11-testing.md`](11-testing.md) is stale (§10) and should be rewritten from the actual `backend/tests/` contents.
- `:cancel` exists only for Journal Entries and Sales Orders (§5/§8) — Quotations, Purchase Orders, and Sales/Vendor Invoices have no direct cancel path post-issuance; the workaround today is a credit/debit note.
- No CI pipeline (`.github/workflows/` doesn't exist) — verification is currently manual (ruff/tsc/eslint/pytest run by hand before each commit).
- No automatic Fixed-Asset creation from a Purchasing receipt — assets are entered manually today.

## 23. Where to look first for a given kind of change

| You're changing... | Start here |
|---|---|
| A new authenticated endpoint | `identity/api/deps.py`'s `require_permission`, then the target module's `api/routes.py` for the nearest analogous route |
| Anything touching `app_user` pre-login | §5 and §6 — read `set_login_lookup`'s docstring in full first |
| A new audited action | §9 — reuse `AuditLogRepository`, don't build a new mechanism |
| Multi-tenant data access | §5 and [`16-multi-tenancy-hardening.md`](16-multi-tenancy-hardening.md) |
| A new migration | §4 — check the revision-ID collision history first |
| Anything user-facing in Arabic/English | §19 — both `ar.json`/`en.json` keys in the same change |
