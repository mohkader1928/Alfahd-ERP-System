"""Closes docs/16b-idempotency-concurrency-design.md finding #3 (MEDIUM,
ZATCA-compliance-relevant): `_next_icv_and_previous_hash` read the hash
chain's tail with a plain unlocked `ORDER BY icv DESC LIMIT 1`. Two
concurrent invoice issuances for the same company (different orders, so
the already-fixed invoice-duplication guard doesn't apply) could both
read the same tail and compute the same next ICV — breaking the hash
chain's required total order, a ZATCA compliance defect, not just an
internal bookkeeping one.

Fixed by locking the company row as a serialization anchor before
reading the tail (SalesInvoiceService._next_icv_and_previous_hash).
Verified here with genuine concurrent HTTP requests, matching the
established asyncio.gather pattern.
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


async def _create_confirmed_order(client, headers) -> str:
    partner = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "ICV Customer", "is_customer": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{uuid_hex()}", "name": "ICV Product", "sales_price": "50.00"},
    )
    quote = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner.json()["id"],
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product.json()["id"], "qty": "1", "unit_price": "50.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_resp = await client.post(f"/api/v1/sales/quotations/{quote.json()['id']}:confirm", headers=headers)
    return order_resp.json()["id"]


async def test_sequential_invoices_get_strictly_incrementing_icv(client):
    env = await _bootstrap(client, f"Sequential-{uuid_hex()}")
    icvs = []
    for _ in range(3):
        order_id = await _create_confirmed_order(client, env["headers"])
        resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=env["headers"])
        assert resp.status_code == 201
        icvs.append(resp.json()["zatca_submission"]["icv"])
    assert icvs == sorted(set(icvs)) and len(icvs) == len(set(icvs)), f"expected strictly distinct, increasing ICVs, got {icvs}"


async def test_concurrent_invoices_for_same_company_never_share_an_icv(client):
    """Genuine concurrency: two different orders for the same company,
    invoiced simultaneously. The already-fixed invoice-duplication guard
    doesn't apply here (different orders) — this isolates the ICV race
    specifically. Both requests can still legitimately collide on the
    orthogonal, already-accepted count(*)+1 *number* race (same class as
    every other document type, closed by a clean retryable 422 rather
    than a duplicate) — that is not what this test is about. What must
    never happen, with or without a number collision, is a raw 500 or
    two *successful* invoices sharing one ICV."""
    env = await _bootstrap(client, f"Concurrent-{uuid_hex()}")
    order_a = await _create_confirmed_order(client, env["headers"])
    order_b = await _create_confirmed_order(client, env["headers"])

    responses = await asyncio.gather(
        client.post(f"/api/v1/sales/orders/{order_a}:invoice", headers=env["headers"]),
        client.post(f"/api/v1/sales/orders/{order_b}:invoice", headers=env["headers"]),
        return_exceptions=True,
    )
    statuses = [r.status_code for r in responses if not isinstance(r, Exception)]
    assert all(s in (201, 422) for s in statuses), f"unexpected status among {statuses}"

    icvs = [r.json()["zatca_submission"]["icv"] for r in responses if not isinstance(r, Exception) and r.status_code == 201]
    assert len(icvs) == len(set(icvs)), f"two successful invoices shared an ICV: {icvs}"
