"""Idempotency-Key mechanism (docs/16b-idempotency-concurrency-design.md,
MUST-priority: `POST /sales/invoices/{id}:credit-note`).

Unlike sales invoice issuance — closed via a simple order.status guard +
DB constraint, because invoicing the same order twice is always wrong —
a second credit note against the same invoice can be entirely legitimate
(partial returns, separate corrections issued on different days). A
"block any second credit note" guard would be a functional regression,
not a fix, so this endpoint needed the full Idempotency-Key mechanism
instead: an opt-in `Idempotency-Key` header that makes a genuine retry
(same key, same body) return the original response without a second
side effect, while a deliberate second credit note (no header, or a
different key) still works exactly as before.
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


async def _bootstrap_with_invoice(client, label: str) -> dict:
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

    partner = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Credit Note Customer", "is_customer": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{uuid_hex()}", "name": "Credit Note Product", "sales_price": "100.00"},
    )
    quote = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner.json()["id"],
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product.json()["id"], "qty": "2", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice = (await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)).json()["invoice"]

    return {"headers": headers, "invoice_id": invoice["id"]}


async def test_credit_note_without_key_behaves_exactly_as_before(client):
    env = await _bootstrap_with_invoice(client, f"NoKey-{uuid_hex()}")
    resp = await client.post(
        f"/api/v1/sales/invoices/{env['invoice_id']}:credit-note",
        headers=env["headers"],
        json={"reason": "Damaged goods"},
    )
    assert resp.status_code == 201
    assert resp.json()["invoice"]["invoice_type"] == "credit_note"


async def test_two_credit_notes_without_key_are_both_legitimate(client):
    """No header = opt-out, matches the accepted business case: two
    separate corrections against the same invoice both succeed."""
    env = await _bootstrap_with_invoice(client, f"TwoNotes-{uuid_hex()}")
    first = await client.post(
        f"/api/v1/sales/invoices/{env['invoice_id']}:credit-note",
        headers=env["headers"],
        json={"reason": "Partial return - item A"},
    )
    second = await client.post(
        f"/api/v1/sales/invoices/{env['invoice_id']}:credit-note",
        headers=env["headers"],
        json={"reason": "Partial return - item B"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["invoice"]["id"] != second.json()["invoice"]["id"]


async def test_same_key_same_body_retried_sequentially_replays_response(client):
    env = await _bootstrap_with_invoice(client, f"Replay-{uuid_hex()}")
    idem_headers = {**env["headers"], "Idempotency-Key": "retry-key-1"}
    body = {"reason": "Wrong price charged"}

    first = await client.post(f"/api/v1/sales/invoices/{env['invoice_id']}:credit-note", headers=idem_headers, json=body)
    second = await client.post(f"/api/v1/sales/invoices/{env['invoice_id']}:credit-note", headers=idem_headers, json=body)

    assert first.status_code == 201
    assert second.status_code == 201
    # Same credit note ID both times — the retry did not create a second one.
    assert first.json()["invoice"]["id"] == second.json()["invoice"]["id"]

    all_invoices = (await client.get("/api/v1/sales/invoices", headers=env["headers"])).json()
    credit_notes = [inv for inv in all_invoices["items"] if inv["invoice_type"] == "credit_note"]
    assert len(credit_notes) == 1


async def test_same_key_different_body_returns_409(client):
    env = await _bootstrap_with_invoice(client, f"Conflict-{uuid_hex()}")
    idem_headers = {**env["headers"], "Idempotency-Key": "retry-key-2"}

    first = await client.post(
        f"/api/v1/sales/invoices/{env['invoice_id']}:credit-note", headers=idem_headers, json={"reason": "Reason A"}
    )
    second = await client.post(
        f"/api/v1/sales/invoices/{env['invoice_id']}:credit-note", headers=idem_headers, json={"reason": "Reason B"}
    )

    assert first.status_code == 201
    assert second.status_code == 409


async def test_concurrent_identical_requests_produce_exactly_one_credit_note(client):
    """Genuine concurrency, not a sequential retry — two truly simultaneous
    requests with the same key must still only ever create one credit
    note, proving the row lock (not just the sequential status check)
    closes this."""
    env = await _bootstrap_with_invoice(client, f"Concurrent-{uuid_hex()}")
    idem_headers = {**env["headers"], "Idempotency-Key": "retry-key-3"}
    body = {"reason": "Concurrent retry"}

    responses = await asyncio.gather(
        client.post(f"/api/v1/sales/invoices/{env['invoice_id']}:credit-note", headers=idem_headers, json=body),
        client.post(f"/api/v1/sales/invoices/{env['invoice_id']}:credit-note", headers=idem_headers, json=body),
        return_exceptions=True,
    )
    statuses = sorted(r.status_code for r in responses if not isinstance(r, Exception))
    assert statuses == [201, 201], f"both should report success (one real, one replayed), got {statuses}"

    all_invoices = (await client.get("/api/v1/sales/invoices", headers=env["headers"])).json()
    credit_notes = [inv for inv in all_invoices["items"] if inv["invoice_type"] == "credit_note"]
    assert len(credit_notes) == 1, f"expected exactly 1 credit note, found {len(credit_notes)}"
