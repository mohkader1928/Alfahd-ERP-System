# Release Manifest — phase-one-v1.0.0

Stage 0 (Golden Baseline Protection) artifact. This file is the single
source of truth for "what exactly is v1.0.0" — every field below was
verified directly against the repository and the running stack, not copied
from another document. Re-verify with the commands shown before trusting
this file after any further commits.

## Identity

| Field | Value | Verified via |
|---|---|---|
| Release version | `phase-one-v1.0.0` | `git tag` |
| Git SHA | `6b6403cb4b4d75e1f53a5d86ff17e574cd37c881` | `git rev-parse HEAD` |
| Git tag | `phase-one-v1.0.0` (annotated, points at the SHA above) | `git rev-parse phase-one-v1.0.0^{commit}` |
| `origin/main` | `6b6403cb4b4d75e1f53a5d86ff17e574cd37c881` (identical to HEAD) | `git rev-parse origin/main` |
| Migration head (static, from files) | `a8b9c0d1e2f3` (`password_reset_and_login_lockout`) | single linear chain, 50 files, no branching — see `backend/migrations/versions/` |
| Migration head (live database) | `a8b9c0d1e2f3` — **matches** static head | `SELECT version_num FROM alembic_version;` against `erp-nucleus-postgres-1` |

Reproducibility: `git checkout phase-one-v1.0.0` + `alembic upgrade head` against a
fresh database deterministically reconstructs this exact state — confirmed
by the live-DB check above matching the static file-derived head.

## Component versions

| Component | Version | Source |
|---|---|---|
| Backend package version | `0.1.0` | `backend/pyproject.toml` |
| Frontend package version | `0.1.0` | `frontend/package.json` |
| Python | `3.12` (`>=3.12,<3.13`) | `backend/pyproject.toml` (`requires-python`), `backend/Dockerfile` (`python:3.12-slim`) |
| Node.js | `22` | `frontend/Dockerfile` (`node:22-slim`) |
| PostgreSQL (image) | `postgres:16-alpine` | `infra/docker-compose.yml`, `infra/docker-compose.prod.yml` |
| PostgreSQL (live, verified) | `16.14` (Alpine build) | `SELECT version();` against `erp-nucleus-postgres-1` |
| Redis | `redis:7-alpine` | `infra/docker-compose.yml`, `infra/docker-compose.prod.yml` |
| nginx (prod reverse proxy) | `nginx:1.27-alpine` | `infra/docker-compose.prod.yml` |
| FastAPI | `>=0.115.0` | `backend/pyproject.toml` |
| SQLAlchemy | `>=2.0.35` (async) | `backend/pyproject.toml` |
| Alembic | `>=1.13.3` | `backend/pyproject.toml` |
| Next.js | `16.2.12` | `frontend/package.json` |
| React | `19.2.4` | `frontend/package.json` |

**Known gap:** `backend/pyproject.toml` and `frontend/package.json` both
carry the generic package version `0.1.0` — neither was bumped to reflect
`phase-one-v1.0.0`. The git tag is the only authoritative version identity
today; there is no in-application `/version` endpoint or `VERSION` file.
Not changed as part of Stage 0 (a version-string bump is metadata-only and
low-risk, but it wasn't asked for and touches tracked build-config files —
flagging it here rather than acting on it unilaterally).

## Deployment method

- **Dev**: `infra/docker-compose.yml` (Compose project `erp-nucleus`) — `postgres`, `redis`, `api`, `worker`, plus a one-off `migrate` profile service. Source bind-mounted into `api`/`worker`.
- **Prod**: `infra/docker-compose.prod.yml` (Compose project `erp-nucleus-prod`) — adds `frontend` and `nginx` (reverse proxy, port 80), images built with `target: production`, no bind mounts. See [`docs/14-deployment.md`](14-deployment.md) for full deploy steps.
- Migrations are a deliberate, separate step (`docker compose run --rm migrate`) — never run implicitly on `up`.

## Required environment variables (names only — no values/secrets)

**`backend/.env`** (dev) / **`backend/.env.production`** (prod runtime role, `erp_app`):
`DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`, `APP_ENV`, `LOG_LEVEL`, `CORS_ORIGINS`

**`backend/.env.migrate`** (dev) / **`backend/.env.migrate.production`** (migration role, `erp_migrate`, plus bootstrap superuser):
`DATABASE_URL_BOOTSTRAP_SYNC`, `POSTGRES_DB`, `ERP_MIGRATE_PASSWORD`, `ERP_APP_PASSWORD`, `DATABASE_URL_MIGRATE_SYNC`, `DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`, `APP_ENV`, `LOG_LEVEL`

**`infra/.env`** (prod, compose-level):
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `NEXT_PUBLIC_API_URL`, `HTTP_PORT`

All names confirmed against `backend/.env.example` and `backend/.env.migrate.example` (tracked, placeholder values only) plus the variable *names* (values redacted) in the gitignored `.env.production`/`.env.migrate.production` actually in use locally. No secret value appears in this manifest or was printed to any log by Stage 0 tooling.

## Test status

- **466 test functions** across `backend/tests/` (53 files + `conftest.py`) — static count via `grep -rc "^async def test_\|^def test_"`, matches the figure previously cited in release/audit docs.
- **Live run, verified in Stage 0**: `466 passed, 0 failed` (966s / ~16 min) — run inside the isolated Stage 0 restore-test environment (a fresh Postgres 16 instance, restored from a real backup of this database, entirely separate from the live dev database — see `docs/21-disaster-recovery-and-rollback.md` and the Stage 0 Final Report), not against the live dev database, so the run doesn't write test data into it.
- CI (`.github/workflows/ci.yml`, added in Stage 0) now runs `ruff check src/`, `pytest`, frontend `tsc --noEmit`, and `eslint` on every push/PR to `main` — see the Stage 0 Final Report for what has and hasn't yet been observed running on GitHub itself (the workflow's commands were validated locally/in the restore environment before being committed, but its first real run on GitHub Actions happens only after this branch is pushed).

## Known limitations (carried from the Adaptive ERP Architecture Impact Assessment)

- No backup/restore procedure existed before Stage 0 — this manifest and the accompanying `infra/backup/` scripts are that procedure's first version.
- No CI/CD pipeline — tests, `ruff`, and frontend typecheck/lint are documented and runnable but not automated on push (Stage 0-G addresses this at a minimal level; see the Stage 0 final report for what was actually wired up vs. only designed).
- Audit trail (`AuditLogRepository.record()`) is called explicitly per-endpoint, not enforced by a framework-level hook — coverage depends on each router remembering to call it.
- No rate limiting anywhere in the API.
- `backend/pyproject.toml` / `frontend/package.json` versions are not synced to the release tag (see above).

## How to reproduce this manifest

```bash
git rev-parse HEAD origin/main phase-one-v1.0.0^{commit}
docker exec erp-nucleus-postgres-1 psql -U erp -d erp_nucleus -c "SELECT version_num FROM alembic_version;"
docker exec erp-nucleus-postgres-1 psql -U erp -d erp_nucleus -c "SELECT version();"
grep -rc "^async def test_\|^def test_" backend/tests | awk -F: '{s+=$2} END {print s}'
```
