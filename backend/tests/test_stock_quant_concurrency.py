"""Targeted fix for the stock_quant lost-update race found in the Phase 16B
design audit (docs/16b-idempotency-concurrency-design.md, Critical Race
Condition #2, ranked HIGH): `receive_stock`/`issue_stock` read
`quant.qty_on_hand` with a plain unlocked SELECT, then wrote it back later
in the same transaction. Two genuinely concurrent moves against the same
product+location could both read the same starting quantity and one
write silently clobbers the other's — a real, "two warehouse staff acting
on the same product near-simultaneously" scenario, not a corner case.

Fix: `StockQuantRepository.get_or_create_for_update` takes a row-level
`SELECT ... FOR UPDATE` lock before either service method reads
`qty_on_hand`, serializing concurrent writers instead of losing one's
update.

Like test_invoice_duplicate_prevention.py, the concurrent test here fires
genuine simultaneous HTTP requests via asyncio.gather() over a shared
AsyncClient/ASGITransport — each gets its own DB session through the
app's normal get_db() dependency, exactly like two real concurrent
clients.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from tests.conftest import unique_email, unique_vat


@pytest.fixture(scope="module")
async def client():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


async def _bootstrap_with_warehouse(client, label: str) -> dict:
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

    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{uuid_hex()}", "name": f"{label} Product", "sales_price": "50.00"},
    )
    product_id = product_resp.json()["id"]

    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": f"{label} Warehouse", "is_default": True}
    )
    location_id = wh_resp.json()["default_location"]["id"]

    return {"headers": headers, "product_id": product_id, "location_id": location_id}


async def test_normal_sequential_receipts_sum_correctly(client):
    env = await _bootstrap_with_warehouse(client, f"Sequential-{uuid_hex()}")

    for _ in range(2):
        resp = await client.post(
            "/api/v1/inventory/stock/receive",
            headers=env["headers"],
            json={"product_id": env["product_id"], "location_id": env["location_id"], "qty": "10", "unit_cost": "5.00"},
        )
        assert resp.status_code == 201

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=env["headers"])).json()
    quant = next(q for q in quants if q["product_id"] == env["product_id"])
    assert quant["qty_on_hand"] == "20.000000"


async def test_concurrent_receipts_do_not_lose_an_update(client):
    """The scenario the old unlocked SELECT could not close: two genuinely
    simultaneous receipts of the same product+location both read
    qty_on_hand=0 before either commits, and without the row lock, the
    second write would clobber the first (final qty = 15, not 25)."""
    env = await _bootstrap_with_warehouse(client, f"Concurrent-{uuid_hex()}")

    responses = await asyncio.gather(
        client.post(
            "/api/v1/inventory/stock/receive",
            headers=env["headers"],
            json={"product_id": env["product_id"], "location_id": env["location_id"], "qty": "10", "unit_cost": "5.00"},
        ),
        client.post(
            "/api/v1/inventory/stock/receive",
            headers=env["headers"],
            json={"product_id": env["product_id"], "location_id": env["location_id"], "qty": "15", "unit_cost": "6.00"},
        ),
        return_exceptions=True,
    )

    statuses = [r.status_code for r in responses if not isinstance(r, Exception)]
    assert statuses == [201, 201], f"both concurrent receipts should succeed, got {statuses}"

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=env["headers"])).json()
    quant = next(q for q in quants if q["product_id"] == env["product_id"])
    # Both quantities must be reflected — a lost update would show 10 or 15,
    # not 25.
    assert quant["qty_on_hand"] == "25.000000"


async def test_concurrent_receipts_different_products_are_unaffected(client):
    """The lock is per (product_id, location_id) — two different products
    receiving concurrently must not serialize against each other or
    otherwise interfere."""
    env = await _bootstrap_with_warehouse(client, f"Independent-{uuid_hex()}")
    product_b_resp = await client.post(
        "/api/v1/identity/products",
        headers=env["headers"],
        json={"sku": f"SKU-{uuid_hex()}", "name": "Second Product", "sales_price": "20.00"},
    )
    product_b_id = product_b_resp.json()["id"]

    responses = await asyncio.gather(
        client.post(
            "/api/v1/inventory/stock/receive",
            headers=env["headers"],
            json={"product_id": env["product_id"], "location_id": env["location_id"], "qty": "5", "unit_cost": "2.00"},
        ),
        client.post(
            "/api/v1/inventory/stock/receive",
            headers=env["headers"],
            json={"product_id": product_b_id, "location_id": env["location_id"], "qty": "8", "unit_cost": "3.00"},
        ),
    )
    assert all(r.status_code == 201 for r in responses)

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=env["headers"])).json()
    quant_a = next(q for q in quants if q["product_id"] == env["product_id"])
    quant_b = next(q for q in quants if q["product_id"] == product_b_id)
    assert quant_a["qty_on_hand"] == "5.000000"
    assert quant_b["qty_on_hand"] == "8.000000"
