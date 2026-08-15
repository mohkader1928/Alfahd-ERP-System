"""Shared test fixtures.

Runs against the same Postgres instance as dev (service name `postgres` in
docker-compose), using randomized VAT/email values per test so runs don't
collide. A fully isolated test database + migration-per-run harness is a
reasonable next hardening step, but not required to validate M0 behavior.

Catalog seeding (currencies, account types, the permission catalog — see
`src/shared/infrastructure/db/seed.py`) normally happens in `src/api/main.py`'s
FastAPI `lifespan`, which only runs on a real ASGI startup (`uvicorn`, or a
lifespan-aware test client). The `client` fixture below wraps `app` directly
in `httpx.ASGITransport` without driving lifespan events, so on a database
that has never had a real server start against it (a fresh CI database, most
notably — this went unnoticed for a long time because the shared dev
database above had already been seeded by years of real `uvicorn` runs), the
catalog was simply never there and every test touching it failed. The
session-scoped fixture below closes that gap by calling `seed_core_data()` —
already written and documented as "a single entry point for tests" in
`seed.py`, just never actually wired up here — once per test run, before any
test executes. No new seeding logic; no production code path changed.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from src.shared.infrastructure.db.seed import seed_core_data
from src.shared.infrastructure.db.session import AsyncSessionLocal


@pytest.fixture(scope="session", autouse=True)
async def _seed_catalog_data_once():
    async with AsyncSessionLocal() as session:
        await seed_core_data(session)


@pytest.fixture
async def client():
    # raise_app_exceptions=False so unhandled exceptions come back as the
    # real HTTP 500 response (via our registered exception handler) instead
    # of being re-raised into the test — matching production behavior under
    # uvicorn, where they never propagate to the caller either.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def unique_vat() -> str:
    return str(uuid.uuid4().int)[:15]


def unique_email() -> str:
    return f"admin-{uuid.uuid4().hex[:10]}@test-erp.sa"
