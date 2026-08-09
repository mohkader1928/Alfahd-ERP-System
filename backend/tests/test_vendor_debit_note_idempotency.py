"""Idempotency-Key mechanism for POST /purchasing/vendor-bills/{id}:debit-note
(P0-2 audit finding: the endpoint mirrored issue_credit_note's accounting
and AP-aging behavior exactly, but not the Idempotency-Key protection
docs/16b-idempotency-concurrency-design.md calls MUST-priority for this
exact class of endpoint).

Unlike vendor bill approval — closed by a status guard, because approving
the same bill twice is always wrong — a second debit note against the
same posted bill can be entirely legitimate (separate returns, separate
price corrections), so a "block any second debit note" guard would be a
functional regression. Mirrors test_credit_note_idempotency.py's shape
exactly, on top of the procure-to-pay bootstrap from
test_vendor_debit_note.py.
"""

import asyncio

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client, label: str):
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
    return company_id, headers


async def _create_posted_bill(client, headers) -> str:
    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Idempotency Vendor", "is_vendor": True}
    )
    vendor_id = vendor_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Idempotency Product", "sales_price": "50.00"},
    )
    product_id = product_resp.json()["id"]
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True})

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "10", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]

    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "10"}]},
    )
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "INV-IDEM", "lines": [{"purchase_order_line_id": po_line_id, "qty": "10", "unit_price": "20.00"}]},
    )
    bill_id = bill_resp.json()["id"]
    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)
    assert approve_resp.json()["status"] == "posted"
    return bill_id


async def test_debit_note_without_key_behaves_exactly_as_before(client):
    _, headers = await _bootstrap_and_login(client, "NoKey")
    bill_id = await _create_posted_bill(client, headers)

    resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=headers, json={"reason": "Damaged goods"}
    )
    assert resp.status_code == 201
    assert resp.json()["bill_type"] == "debit_note"


async def test_two_debit_notes_without_key_are_both_legitimate(client):
    """No header = opt-out, matches the accepted business case: two
    separate corrections against the same bill both succeed."""
    _, headers = await _bootstrap_and_login(client, "TwoNotes")
    bill_id = await _create_posted_bill(client, headers)

    first = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=headers, json={"reason": "Partial return A"}
    )
    second = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=headers, json={"reason": "Partial return B"}
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


async def test_same_key_same_body_retried_sequentially_replays_response(client):
    _, headers = await _bootstrap_and_login(client, "Replay")
    bill_id = await _create_posted_bill(client, headers)
    idem_headers = {**headers, "Idempotency-Key": "retry-key-1"}
    body = {"reason": "Wrong price charged"}

    first = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=idem_headers, json=body)
    second = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=idem_headers, json=body)

    assert first.status_code == 201
    assert second.status_code == 201
    # Same debit note ID both times -- the retry did not create a second one.
    assert first.json()["id"] == second.json()["id"]

    all_bills = (await client.get("/api/v1/purchasing/vendor-bills", headers=headers)).json()
    debit_notes = [b for b in all_bills["items"] if b["bill_type"] == "debit_note"]
    assert len(debit_notes) == 1


async def test_same_key_different_body_returns_409(client):
    _, headers = await _bootstrap_and_login(client, "Conflict")
    bill_id = await _create_posted_bill(client, headers)
    idem_headers = {**headers, "Idempotency-Key": "retry-key-2"}

    first = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=idem_headers, json={"reason": "Reason A"}
    )
    second = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=idem_headers, json={"reason": "Reason B"}
    )

    assert first.status_code == 201
    assert second.status_code == 409


async def test_concurrent_identical_requests_produce_exactly_one_debit_note(client):
    """Genuine concurrency, not a sequential retry -- two truly simultaneous
    requests with the same key must still only ever create one debit note,
    proving the row lock (not just the sequential status check) closes
    this."""
    _, headers = await _bootstrap_and_login(client, "Concurrent")
    bill_id = await _create_posted_bill(client, headers)
    idem_headers = {**headers, "Idempotency-Key": "retry-key-3"}
    body = {"reason": "Concurrent retry"}

    responses = await asyncio.gather(
        client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=idem_headers, json=body),
        client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note", headers=idem_headers, json=body),
        return_exceptions=True,
    )
    statuses = sorted(r.status_code for r in responses if not isinstance(r, Exception))
    assert statuses == [201, 201], f"both should report success (one real, one replayed), got {statuses}"

    all_bills = (await client.get("/api/v1/purchasing/vendor-bills", headers=headers)).json()
    debit_notes = [b for b in all_bills["items"] if b["bill_type"] == "debit_note"]
    assert len(debit_notes) == 1, f"expected exactly 1 debit note, found {len(debit_notes)}"
