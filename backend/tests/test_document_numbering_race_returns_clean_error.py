"""Closes the remaining gap from docs/16b-idempotency-concurrency-design.md's
Database Constraints table: every numbered document already has a
`UNIQUE(company_id, number)` constraint (the actual guarantee against a
duplicate number — count(*)+1 numbering is a real race, confirmed by
tracing the code, but the constraint makes a collision impossible to
persist). What was still missing: nothing translated the constraint
violation into a clean error for 5 of the 6 document types (only sales
invoice issuance had this, from an earlier fix) — a losing concurrent
request got a raw, unhandled `IntegrityError`, surfacing as a bare 500
instead of a clean, retryable 422.

Fired as genuine concurrent HTTP requests (asyncio.gather over a shared
AsyncClient/ASGITransport, matching test_invoice_duplicate_prevention.py
and test_stock_quant_concurrency.py) rather than asserting a guaranteed
collision (count(*)-based numbering racing under async I/O scheduling
isn't reliably deterministic) — the real, always-true assertion is that
nothing ever 500s and every document that does get created has a unique
number, whether or not this particular run happened to collide.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
async def client():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


async def _bootstrap(client, label: str) -> dict:
    payload = {
        "tenant_legal_name": f"{label} Holding",
        "company_legal_name": f"{label} Trading Co.",
        "company_legal_name_ar": f"{label} Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": f"{label} Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201
    company_id = boot_resp.json()["company_id"]
    branch_id = boot_resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return {"headers": headers}


async def test_concurrent_quotation_creation_never_500s(client):
    env = await _bootstrap(client, f"QuoteRace-{uuid_hex()}")
    partner = await client.post(
        "/api/v1/identity/partners", headers=env["headers"], json={"name": "Race Customer", "is_customer": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=env["headers"],
        json={"sku": f"SKU-{uuid_hex()}", "name": "Race Product", "sales_price": "10.00"},
    )

    def _create():
        return client.post(
            "/api/v1/sales/quotations",
            headers=env["headers"],
            json={
                "partner_id": partner.json()["id"],
                "quote_date": "2026-06-01",
                "lines": [{"product_id": product.json()["id"], "qty": "1", "unit_price": "10.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
            },
        )

    responses = await asyncio.gather(*[_create() for _ in range(6)], return_exceptions=True)
    statuses = [r.status_code for r in responses if not isinstance(r, Exception)]
    # The real guarantee: never a raw 500, whether or not this run happened
    # to collide (a collision cleanly resolves to 422, not a crash).
    assert all(s in (201, 422) for s in statuses), f"unexpected status among {statuses}"

    created_numbers = [r.json()["number"] for r in responses if not isinstance(r, Exception) and r.status_code == 201]
    assert len(created_numbers) == len(set(created_numbers)), "duplicate quotation numbers persisted"


async def test_concurrent_purchase_order_creation_never_500s(client):
    env = await _bootstrap(client, f"PORace-{uuid_hex()}")
    vendor = await client.post(
        "/api/v1/identity/partners", headers=env["headers"], json={"name": "Race Vendor", "is_vendor": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=env["headers"],
        json={"sku": f"SKU-{uuid_hex()}", "name": "Race Product", "cost_price": "10.00"},
    )

    def _create():
        return client.post(
            "/api/v1/purchasing/orders",
            headers=env["headers"],
            json={
                "partner_id": vendor.json()["id"],
                "order_date": "2026-06-01",
                "lines": [{"product_id": product.json()["id"], "qty": "1", "unit_price": "10.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
            },
        )

    responses = await asyncio.gather(*[_create() for _ in range(6)], return_exceptions=True)
    statuses = [r.status_code for r in responses if not isinstance(r, Exception)]
    assert all(s in (201, 422) for s in statuses), f"unexpected status among {statuses}"

    created_numbers = [r.json()["number"] for r in responses if not isinstance(r, Exception) and r.status_code == 201]
    assert len(created_numbers) == len(set(created_numbers)), "duplicate purchase order numbers persisted"


async def test_concurrent_payment_creation_never_500s(client):
    env = await _bootstrap(client, f"PayRace-{uuid_hex()}")
    partner = await client.post(
        "/api/v1/identity/partners", headers=env["headers"], json={"name": "Race Payer", "is_customer": True}
    )
    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=env["headers"])).json()
    cash_account = next(a for a in accounts if a["code"] == "1000")

    def _create():
        return client.post(
            "/api/v1/payments/payments",
            headers=env["headers"],
            json={
                "partner_id": partner.json()["id"],
                "payment_type": "customer",
                "payment_date": "2026-06-01",
                "amount": "50.00",
                "account_id": cash_account["id"],
                "allocations": [],
            },
        )

    responses = await asyncio.gather(*[_create() for _ in range(6)], return_exceptions=True)
    statuses = [r.status_code for r in responses if not isinstance(r, Exception)]
    assert all(s in (201, 422) for s in statuses), f"unexpected status among {statuses}"

    created_numbers = [r.json()["number"] for r in responses if not isinstance(r, Exception) and r.status_code == 201]
    assert len(created_numbers) == len(set(created_numbers)), "duplicate payment numbers persisted"
