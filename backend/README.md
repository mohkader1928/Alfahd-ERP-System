# Backend — FastAPI

Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16 with Row-Level
Security for multi-tenant isolation. See [`../docs/08-system-architecture.md`](../docs/08-system-architecture.md)
for the full architecture and [`../docs/09-folder-structure.md`](../docs/09-folder-structure.md)
for why each module is laid out the way it is.

## Setup

Requires Docker (for Postgres/Redis) and either `uv` or a Python 3.12
virtualenv if you want to run the API outside its container.

```bash
# Everything via Docker (recommended — matches CI/prod dependency versions)
cd ../infra
docker compose up -d

# Or locally, against the dockerized Postgres/Redis:
uv pip install -e ".[dev]"
uvicorn src.api.main:app --reload
```

Copy `.env.example` to `.env` for local dev (already gitignored). For a
production `.env.production`, see [`../docs/14-deployment.md`](../docs/14-deployment.md).

## Common commands

```bash
# Run the full test suite (against the real dockerized Postgres, not mocks)
docker compose -f ../infra/docker-compose.yml exec api pytest -q

# ...with coverage
docker compose -f ../infra/docker-compose.yml exec api pytest -q --cov=src/modules --cov-report=term-missing

# Lint
docker compose -f ../infra/docker-compose.yml exec api ruff check src tests

# New migration after changing models (read-only schema introspection +
# a local file write — fine via the already-running api container)
docker compose -f ../infra/docker-compose.yml exec api alembic revision --autogenerate -m "description"

# Apply migrations — a dedicated one-off service, NOT `exec api`: the API
# container's runtime role (erp_app) is deliberately restricted and can't
# run DDL. See ../docs/17c-rls-runtime-role-hardening.md.
docker compose -f ../infra/docker-compose.yml --profile tools run --rm migrate
```

Interactive API docs (Swagger UI): http://localhost:8000/docs — this is the
authoritative, always-current API reference (generated from the Pydantic
schemas and route definitions, not hand-maintained — NFR-MAINT-004).

## Module structure

Every module under `src/modules/` follows the same four layers:

```
modules/<name>/
├── domain/            # entities, value objects, pure business rules — no I/O
├── application/        # services.py — orchestration, calls repos + domain
├── infrastructure/     # SQLAlchemy models.py, repositories.py
└── api/                 # routes.py (FastAPI router), schemas.py (Pydantic), deps.py
```

Cross-module dependencies are one-way and enforced by convention (not yet
by a lint rule): `identity` has zero dependencies on other modules;
`accounting` depends only on `identity`; `sales` depends on
`identity + inventory + accounting + zatca`; `purchasing` depends on
`identity + inventory + accounting`; `reporting` is the only module allowed
to read across all others. See
[`../docs/08-system-architecture.md`](../docs/08-system-architecture.md)
for the full dependency map and the reasoning (e.g. why Accounting
subscribes to Identity's `CompanyRegistered` domain event instead of
Identity importing Accounting).

Adding a new module (from the deferred backlog — CRM, POS, HR, etc.) means
adding a new folder here and one line in `src/api/main.py`'s
`ENABLED_MODULES` — no existing module's files should need to change.
