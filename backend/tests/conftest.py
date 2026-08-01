"""Shared test fixtures.

Runs against the same Postgres instance as dev (service name `postgres` in
docker-compose), using randomized VAT/email values per test so runs don't
collide. A fully isolated test database + migration-per-run harness is a
reasonable next hardening step, but not required to validate M0 behavior.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app


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
