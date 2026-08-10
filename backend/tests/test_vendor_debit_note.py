"""Vendor Debit Note — Product Owner audit finding: Sales already had a
Credit Note (reverses a posted invoice) but Purchasing had no equivalent
for reversing a posted vendor bill (goods returned to a vendor, or a
price correction) — a real asymmetry against SAP B1/Dynamics 365 BC/Odoo.
Mirrors test_credit_note_reverses_the_original_invoice_journal_entry.py's
shape, built on the same procure-to-pay setup already established in
test_purchasing_m4_smoke.py.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Debit Note Test Holding",
        "company_legal_name": "Debit Note Test Trading Co.",
        "company_legal_name_ar": "Debit Note Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Debit Note Test Admin",
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


async def _create_vendor(client, headers) -> str:
    resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Steel Supplier LLC", "is_vendor": True}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_product(client, headers) -> str:
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Steel Rod", "sales_price": "50.00"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_posted_bill(client, headers) -> tuple[str, str]:
    """Returns (bill_id, vendor_id) for a fully procured-to-pay, posted bill:
    qty=100 @ 20.00 -> subtotal 2000, tax 300 (15%), total 2300."""
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True})

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "100", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)

    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]

    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "100"}]},
    )

    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "INV-9001", "lines": [{"purchase_order_line_id": po_line_id, "qty": "100", "unit_price": "20.00"}]},
    )
    bill_id = bill_resp.json()["id"]

    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)
    assert approve_resp.json()["status"] == "posted"

    return bill_id, vendor_id


async def test_debit_note_reverses_the_original_bill_journal_entry(client):
    _, headers = await _bootstrap_and_login(client)
    bill_id, _ = await _create_posted_bill(client, headers)

    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "Damaged goods returned to vendor"},
    )
    assert debit_resp.status_code == 201
    debit_body = debit_resp.json()
    assert debit_body["bill_type"] == "debit_note"
    assert debit_body["original_bill_id"] == bill_id
    assert debit_body["status"] == "posted"
    assert debit_body["total_amount"] == "2300.0000"

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    # Bill (Cr 2300) + Debit Note (Dr 2300) nets Accounts Payable to zero.
    assert rows["2100"]["total_debit"] == rows["2100"]["total_credit"] == "2300.0000"
    # GRNI: receipt accrual (Cr 2000) + bill's own clearing (Dr 2000) +
    # debit note's AP reversal (Cr 2000) + restock's reversal (P0-9,
    # Dr 2000, since debit_note's default restock=True actually removes
    # the goods from stock too) -> debit 4000, credit 4000.
    assert rows["2300"]["total_debit"] == "4000.0000"
    assert rows["2300"]["total_credit"] == "4000.0000"
    # VAT: bill's Dr 300 (input VAT) + debit note's Cr 300 (reversal) nets to zero net movement.
    assert rows["2200"]["total_debit"] == "300.0000"
    assert rows["2200"]["total_credit"] == "300.0000"
    # P0-9 Purchase Return: Inventory received 2000 at goods-receipt time,
    # then returned right back out at the same (only-ever) average cost —
    # nets to zero, but both legs are real, separate postings.
    assert rows["1300"]["total_debit"] == "2000.0000"
    assert rows["1300"]["total_credit"] == "2000.0000"


async def test_list_vendor_bills_filters_by_bill_type_for_the_returns_screen(client):
    """P0-9 Owner follow-up: the dedicated Purchase Returns screen needs
    to ask the list endpoint for exactly the debit notes, not fetch
    everything and filter client-side."""
    _, headers = await _bootstrap_and_login(client)
    bill_id, _ = await _create_posted_bill(client, headers)
    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "Return", "restock": False},
    )
    debit_note_id = debit_resp.json()["id"]

    returns_resp = await client.get(
        "/api/v1/purchasing/vendor-bills", headers=headers, params={"bill_type": "debit_note"}
    )
    assert returns_resp.status_code == 200
    returns_ids = {row["id"] for row in returns_resp.json()["items"]}
    assert returns_ids == {debit_note_id}  # the original bill must NOT appear


async def test_debit_note_restocks_inventory_by_default(client):
    _, headers = await _bootstrap_and_login(client)
    bill_id, _ = await _create_posted_bill(client, headers)
    product_resp = await client.get("/api/v1/identity/products", headers=headers)
    product_id = next(p["id"] for p in product_resp.json() if p["name"] == "Steel Rod")

    quants_before = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    qty_before = next(q["qty_on_hand"] for q in quants_before if q["product_id"] == product_id)
    assert qty_before == "100.000000"

    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "Damaged goods returned to vendor"},
    )
    assert debit_resp.status_code == 201

    quants_after = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    qty_after = next(q["qty_on_hand"] for q in quants_after if q["product_id"] == product_id)
    assert qty_after == "0.000000"

    moves = (await client.get("/api/v1/inventory/stock/moves", headers=headers, params={"product_id": product_id})).json()
    return_moves = [m for m in moves if m["move_type"] == "return"]
    assert len(return_moves) == 1
    assert return_moves[0]["qty"] == "100.000000"


async def test_debit_note_with_restock_false_leaves_inventory_untouched(client):
    _, headers = await _bootstrap_and_login(client)
    bill_id, _ = await _create_posted_bill(client, headers)
    product_resp = await client.get("/api/v1/identity/products", headers=headers)
    product_id = next(p["id"] for p in product_resp.json() if p["name"] == "Steel Rod")

    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "Price correction only", "restock": False},
    )
    assert debit_resp.status_code == 201

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    qty = next(q["qty_on_hand"] for q in quants if q["product_id"] == product_id)
    assert qty == "100.000000"  # unchanged — still the full original receipt

    moves = (await client.get("/api/v1/inventory/stock/moves", headers=headers, params={"product_id": product_id})).json()
    assert not any(m["move_type"] == "return" for m in moves)


async def test_debit_note_reduces_ap_aging_for_the_original_bill(client):
    _, headers = await _bootstrap_and_login(client)
    bill_id, _ = await _create_posted_bill(client, headers)

    before = await client.get("/api/v1/payments/aging/ap", headers=headers, params={"as_of_date": "2026-12-31"})
    assert any(row["document_id"] == bill_id for row in before.json()["rows"])

    await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "Full return"},
    )

    after = await client.get("/api/v1/payments/aging/ap", headers=headers, params={"as_of_date": "2026-12-31"})
    # Fully debit-noted bill drops out of AP aging entirely (balance <= 0),
    # and the debit note itself is never its own open AP row.
    assert not any(row["document_id"] == bill_id for row in after.json()["rows"])


async def test_debit_note_rejected_against_unposted_bill(client):
    _, headers = await _bootstrap_and_login(client)
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
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
        json={"vendor_reference": "INV-9002", "lines": [{"purchase_order_line_id": po_line_id, "qty": "10", "unit_price": "20.00"}]},
    )
    bill_id = bill_resp.json()["id"]
    assert bill_resp.json()["status"] == "matched"  # never approved/posted

    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "Should be rejected"},
    )
    assert debit_resp.status_code == 422
    assert "posted" in debit_resp.json()["detail"].lower()


async def test_debit_note_rejected_against_another_debit_note(client):
    _, headers = await _bootstrap_and_login(client)
    bill_id, _ = await _create_posted_bill(client, headers)

    first = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "First return"},
    )
    debit_note_id = first.json()["id"]

    second = await client.post(
        f"/api/v1/purchasing/vendor-bills/{debit_note_id}:debit-note",
        headers=headers,
        json={"reason": "Debit note against a debit note"},
    )
    assert second.status_code == 422
    assert "standard" in second.json()["detail"].lower()
