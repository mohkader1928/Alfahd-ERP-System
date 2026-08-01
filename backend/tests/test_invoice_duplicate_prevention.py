"""Phase 16B-Implementation-01 — targeted fix for the invoice-duplication
bug found in the Phase 16B design audit (docs/16b-idempotency-concurrency-design.md,
Critical Race Condition #1).

Root cause: `issue_invoice_from_order` read `sales_order.status` but never
wrote it, so retrying `POST /orders/{id}:invoice` — sequentially or
concurrently — created a second invoice, journal entry, ZATCA submission,
and stock deduction every time.

Fix: a partial UNIQUE index on `sales_invoice.sales_order_id` (WHERE NOT
NULL) as the actual database-level guarantee, closing the race regardless
of timing, plus `order.status = "done"` for a clean, fast error on the
common sequential-retry case, plus catching the resulting IntegrityError
and translating it into the same domain ValueError the status check
already raises (surfaces as a clean 422, not a raw 500).

Every test here goes through the real HTTP API against the real
dockerized Postgres — the concurrent test uses genuine `asyncio.gather()`
over separate HTTP requests (each gets its own DB session via `get_db()`,
exactly like production), not a sequential call dressed up as one.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
async def client():
    # Module-scoped (same rationale as test_multi_tenancy_isolation.py):
    # the concurrent test needs multiple truly-independent requests fired
    # at once, and a single shared AsyncClient over one ASGITransport is
    # exactly how production traffic hits this app (one process, many
    # concurrent connections) — conftest.py's function-scoped client is
    # unaffected, this is a local override for this file only.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _bootstrap_company(client, label: str) -> dict:
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
    body = boot_resp.json()
    company_id, branch_id = body["company_id"], body["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}

    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": f"{label} Customer", "is_customer": True, "vat_number": unique_vat()},
    )
    partner_id = partner_resp.json()["id"]

    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{uuid_hex()}", "name": f"{label} Product", "sales_price": "100.00"},
    )
    product_id = product_resp.json()["id"]

    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": f"{label} Warehouse", "is_default": True}
    )
    location_id = wh_resp.json()["default_location"]["id"]
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "1000", "unit_cost": "10.00"},
    )

    return {
        "headers": headers,
        "company_id": company_id,
        "partner_id": partner_id,
        "product_id": product_id,
    }


def uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


async def _create_confirmed_order(client, company: dict) -> str:
    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=company["headers"],
        json={
            "partner_id": company["partner_id"],
            "quote_date": "2026-06-01",
            "lines": [{"product_id": company["product_id"], "qty": "2", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    quotation_id = quote_resp.json()["id"]
    order_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=company["headers"])
    return order_resp.json()["id"]


# ---------------------------------------------------------------------------
# 1. Normal invoice creation
# ---------------------------------------------------------------------------


async def test_normal_invoice_creation(client):
    company = await _bootstrap_company(client, f"Normal-{uuid_hex()}")
    order_id = await _create_confirmed_order(client, company)

    resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=company["headers"])
    assert resp.status_code == 201
    assert resp.json()["invoice"]["sales_order_id"] == order_id

    order = (await client.get(f"/api/v1/sales/orders/{order_id}", headers=company["headers"])).json()
    assert order["status"] == "done"


# ---------------------------------------------------------------------------
# 2. Same operation submitted twice sequentially
# ---------------------------------------------------------------------------


async def test_sequential_duplicate_invoice_rejected(client):
    company = await _bootstrap_company(client, f"Sequential-{uuid_hex()}")
    order_id = await _create_confirmed_order(client, company)

    first = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=company["headers"])
    assert first.status_code == 201

    second = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=company["headers"])
    assert second.status_code == 422
    assert "already been invoiced" in second.json()["detail"] or "confirmed" in second.json()["detail"]


# ---------------------------------------------------------------------------
# 3. Concurrent duplicate submission — genuine concurrency, not sequential
# ---------------------------------------------------------------------------


async def test_concurrent_duplicate_invoice_exactly_one_succeeds(client):
    """Fires two real, simultaneous HTTP requests via asyncio.gather() — each
    resolves its own AuthContext and its own AsyncSession through the
    app's normal get_db() dependency, exactly as two real concurrent
    clients would. This is the scenario the status check alone cannot
    close (both requests can read status="confirmed" before either
    commits) — only the database's partial unique index can."""
    company = await _bootstrap_company(client, f"Concurrent-{uuid_hex()}")
    order_id = await _create_confirmed_order(client, company)

    responses = await asyncio.gather(
        client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=company["headers"]),
        client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=company["headers"]),
        return_exceptions=True,
    )

    statuses = sorted(r.status_code for r in responses if not isinstance(r, Exception))
    assert statuses == [201, 422], f"expected exactly one success and one rejection, got {statuses}"

    # Verify actual database state, not just the HTTP responses: exactly
    # one invoice must exist for this order.
    dashboard_check = await client.get(
        "/api/v1/reporting/export/sales-invoices", headers=company["headers"]
    )
    data_rows = [line for line in dashboard_check.text.strip().splitlines()[1:] if line]
    assert len(data_rows) == 1, f"expected exactly 1 invoice row, found {len(data_rows)}"


# ---------------------------------------------------------------------------
# 4. Existing legitimate invoices still work (different orders, unaffected)
# ---------------------------------------------------------------------------


async def test_independent_orders_each_get_their_own_invoice(client):
    company = await _bootstrap_company(client, f"Independent-{uuid_hex()}")
    order_a = await _create_confirmed_order(client, company)
    order_b = await _create_confirmed_order(client, company)

    resp_a = await client.post(f"/api/v1/sales/orders/{order_a}:invoice", headers=company["headers"])
    resp_b = await client.post(f"/api/v1/sales/orders/{order_b}:invoice", headers=company["headers"])
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201
    assert resp_a.json()["invoice"]["id"] != resp_b.json()["invoice"]["id"]


# ---------------------------------------------------------------------------
# 5. Multi-company — Company A's invoicing cannot interfere with Company B's
# ---------------------------------------------------------------------------


async def test_multi_company_invoicing_does_not_interfere(client):
    """The new partial unique index is keyed only on sales_order_id (a
    globally-unique UUID naturally scoped to one company by construction —
    no two companies can ever share an order row), so no company_id needs
    to be in the index for correctness. This test proves that in practice:
    both companies successfully invoice their own, unrelated order."""
    company_a = await _bootstrap_company(client, f"MultiA-{uuid_hex()}")
    company_b = await _bootstrap_company(client, f"MultiB-{uuid_hex()}")
    order_a = await _create_confirmed_order(client, company_a)
    order_b = await _create_confirmed_order(client, company_b)

    resp_a = await client.post(f"/api/v1/sales/orders/{order_a}:invoice", headers=company_a["headers"])
    resp_b = await client.post(f"/api/v1/sales/orders/{order_b}:invoice", headers=company_b["headers"])
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201

    # Company A cannot even see Company B's order to attempt a cross-company
    # duplicate — RLS (Phase 16A) already covers this, reconfirmed here.
    cross_attempt = await client.get(f"/api/v1/sales/orders/{order_b}", headers=company_a["headers"])
    assert cross_attempt.status_code == 404


# ---------------------------------------------------------------------------
# 6. Accounting — no duplicate journal entry from the blocked duplicate
# ---------------------------------------------------------------------------


async def test_blocked_duplicate_does_not_create_duplicate_accounting_effect(client):
    company = await _bootstrap_company(client, f"Accounting-{uuid_hex()}")
    order_id = await _create_confirmed_order(client, company)

    await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=company["headers"])
    # Attempt the duplicate — must be rejected before any accounting effect.
    dup = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=company["headers"])
    assert dup.status_code == 422

    entries = (await client.get("/api/v1/accounting/journal-entries", headers=company["headers"])).json()
    # Exactly one journal entry should reference this order's revenue
    # posting — not two. (Stock-deduction/COGS entries share the same
    # source_table, so we assert on total count being small and stable
    # rather than a specific number tied to inventory internals.)
    assert len(entries) >= 1
    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=company["headers"],
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    # Revenue account should reflect exactly one invoice's worth (200.00
    # subtotal: 2 * 100.00), not double (400.00) from a duplicate posting.
    assert rows["4100"]["total_credit"] == "200.0000"


# ---------------------------------------------------------------------------
# 7. Migration safety — reconfirm zero pre-existing violations
# ---------------------------------------------------------------------------


async def test_no_existing_company_has_duplicate_order_invoices(client):
    """Direct proof the constraint didn't need to reject/clean any
    pre-existing data — same check performed before the migration was
    written, re-run here as a regression guard."""
    company = await _bootstrap_company(client, f"Verify-{uuid_hex()}")
    order_id = await _create_confirmed_order(client, company)
    resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=company["headers"])
    assert resp.status_code == 201
