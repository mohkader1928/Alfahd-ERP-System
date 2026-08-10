"""Integration smoke test for Backend M2 — Sales + ZATCA.

Exercises UC-SAL-01/02/03/04/05 end to end: quotation -> sales order ->
invoice, with both the B2B/Clearance path (FR-ZATCA-008) and the
B2C/Reporting path (FR-ZATCA-007), plus the credit note flow and the
posted journal entry (FR-SAL-007).
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Sales Test Holding",
        "company_legal_name": "Sales Test Trading Co.",
        "company_legal_name_ar": "Sales Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Sales Test Admin",
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


async def _create_partner(client, headers, *, is_b2b: bool) -> str:
    resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={
            "name": "Riyadh Steel Co." if is_b2b else "Walk-in Customer",
            "is_customer": True,
            "vat_number": unique_vat() if is_b2b else None,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_product(client, headers) -> str:
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Steel Beam", "sales_price": "1000.00"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _get_tax_rate_id(client, headers) -> str:
    # M1's default seeded tax rates aren't exposed via a dedicated list
    # endpoint in the nucleus yet, so we go through the same chart-of-accounts
    # screen's company scope; a Standard 15% rate always exists post-seed.
    # We fetch it indirectly by trying the journal-entries screen's implicit
    # dependency is not exposed either — so we just look it up directly.
    resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    assert resp.status_code == 200
    # tax rates aren't chart-of-accounts; use a placeholder UUID acceptable
    # to the API (tax_rate_id isn't validated against the DB in this M2 pass —
    # see services.py's flat 15% default). Any well-formed UUID works.
    return "00000000-0000-0000-0000-000000000001"


async def _create_quotation_and_confirm(client, headers, *, partner_id: str, product_id: str, tax_rate_id: str):
    create_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-03-01",
            "lines": [
                {"product_id": product_id, "qty": "2", "unit_price": "1000.00", "tax_rate_id": tax_rate_id}
            ],
        },
    )
    assert create_resp.status_code == 201
    quotation_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "draft"

    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "confirmed"
    return confirm_resp.json()["id"]  # sales_order_id


async def test_b2b_invoice_goes_through_clearance_and_posts_journal_entry(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    order_id = await _create_quotation_and_confirm(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    body = invoice_resp.json()

    assert body["invoice"]["invoice_type"] == "tax"
    assert body["invoice"]["status"] == "cleared"
    assert body["zatca_submission"]["submission_mode"] == "clearance"
    assert body["zatca_submission"]["status"] == "cleared"
    assert body["zatca_submission"]["icv"] == 1
    assert body["zatca_submission"]["qr_payload"]
    assert body["invoice"]["total_amount"] == "2300.00"  # 2*1000 + 15% VAT

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    assert rows["1200"]["total_debit"] == "2300.0000"  # Accounts Receivable
    assert rows["4100"]["total_credit"] == "2000.0000"  # Sales Revenue
    assert rows["2200"]["total_credit"] == "300.0000"  # VAT Payable


async def test_b2c_invoice_is_pending_submission_and_delivered_immediately(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=False)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    order_id = await _create_quotation_and_confirm(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    body = invoice_resp.json()

    assert body["invoice"]["invoice_type"] == "simplified"
    assert body["invoice"]["status"] == "pending_submission"
    assert body["zatca_submission"]["submission_mode"] == "reporting"
    assert body["zatca_submission"]["status"] == "pending_submission"
    # QR/hash are computed locally and available immediately, even though
    # the authority Reporting call hasn't happened yet (FR-ZATCA-007).
    assert body["zatca_submission"]["qr_payload"]
    assert body["zatca_submission"]["invoice_hash"]


async def test_hash_chain_links_sequential_invoices(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    order1_id = await _create_quotation_and_confirm(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )
    invoice1_resp = await client.post(f"/api/v1/sales/orders/{order1_id}:invoice", headers=headers)
    submission1 = invoice1_resp.json()["zatca_submission"]

    order2_id = await _create_quotation_and_confirm(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )
    invoice2_resp = await client.post(f"/api/v1/sales/orders/{order2_id}:invoice", headers=headers)
    submission2 = invoice2_resp.json()["zatca_submission"]

    assert submission1["icv"] == 1
    assert submission2["icv"] == 2
    assert submission2["invoice_hash"] != submission1["invoice_hash"]


async def test_credit_note_reverses_the_original_invoice_journal_entry(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    order_id = await _create_quotation_and_confirm(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    invoice_id = invoice_resp.json()["invoice"]["id"]

    credit_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice_id}:credit-note", headers=headers, json={"reason": "Damaged goods"}
    )
    assert credit_resp.status_code == 201
    credit_body = credit_resp.json()
    assert credit_body["invoice"]["invoice_type"] == "credit_note"
    assert credit_body["invoice"]["original_invoice_id"] == invoice_id
    assert credit_body["invoice"]["status"] == "cleared"

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    # Invoice + credit note should net AR to zero (2300 debit, 2300 credit)
    assert rows["1200"]["total_debit"] == rows["1200"]["total_credit"] == "2300.0000"


# --- P0-9: Sales Return (credit note + restock) ---------------------------


async def _create_quotation_and_confirm_with_qty(
    client, headers, *, partner_id: str, product_id: str, tax_rate_id: str, qty: str
):
    create_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-03-01",
            "lines": [{"product_id": product_id, "qty": qty, "unit_price": "1000.00", "tax_rate_id": tax_rate_id}],
        },
    )
    quotation_id = create_resp.json()["id"]
    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    return confirm_resp.json()["id"]


async def _sell_with_stock(client, headers, *, partner_id: str, product_id: str, tax_rate_id: str):
    """Sets up a default warehouse, receives 10 units at cost 400.00, sells
    2 of them, and returns the invoice_id and the location_id stock was
    issued from — the shared setup for both restock tests below."""
    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True}
    )
    location_id = wh_resp.json()["default_location"]["id"]
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "400.00"},
    )
    order_id = await _create_quotation_and_confirm_with_qty(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id, qty="2"
    )
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    return invoice_resp.json()["invoice"]["id"], location_id


async def test_credit_note_restocks_inventory_and_reverses_cogs_by_default(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)
    invoice_id, _ = await _sell_with_stock(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )

    quants_after_sale = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    qty_after_sale = next(q["qty_on_hand"] for q in quants_after_sale if q["product_id"] == product_id)
    assert qty_after_sale == "8.000000"  # 10 received - 2 sold

    credit_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice_id}:credit-note", headers=headers, json={"reason": "Customer return"}
    )
    assert credit_resp.status_code == 201

    quants_after_return = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    qty_after_return = next(q["qty_on_hand"] for q in quants_after_return if q["product_id"] == product_id)
    assert qty_after_return == "10.000000"  # back to the original 10

    moves = (await client.get("/api/v1/inventory/stock/moves", headers=headers, params={"product_id": product_id})).json()
    return_moves = [m for m in moves if m["move_type"] == "return"]
    assert len(return_moves) == 1
    assert return_moves[0]["qty"] == "2.000000"
    assert return_moves[0]["unit_cost"] == "400.0000"  # exact original cost, not a recomputed one

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    # POST /inventory/stock/receive is a manual, GL-less adjustment (no
    # journal entry of its own) — the only Inventory/COGS postings in this
    # scenario are the sale's own COGS entry and this return's reversal of
    # it: sale Cr 800 (2 @ 400), return Dr 800 -> nets to zero, both real.
    assert rows["1300"]["total_debit"] == "800.0000"
    assert rows["1300"]["total_credit"] == "800.0000"
    # COGS: sale Dr 800, return's reversal Cr 800 -> nets to zero net movement.
    assert rows["5100"]["total_debit"] == "800.0000"
    assert rows["5100"]["total_credit"] == "800.0000"


async def test_credit_note_with_restock_false_leaves_inventory_untouched(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)
    invoice_id, _ = await _sell_with_stock(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )

    credit_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice_id}:credit-note",
        headers=headers,
        json={"reason": "Price correction only", "restock": False},
    )
    assert credit_resp.status_code == 201

    quants = (await client.get("/api/v1/inventory/stock/quants", headers=headers)).json()
    qty = next(q["qty_on_hand"] for q in quants if q["product_id"] == product_id)
    assert qty == "8.000000"  # unchanged — still just the original sale's deduction

    moves = (await client.get("/api/v1/inventory/stock/moves", headers=headers, params={"product_id": product_id})).json()
    assert not any(m["move_type"] == "return" for m in moves)


# --- P0-9 follow-up: freeform Sales Return (no invoice-copy requirement) --


async def test_freeform_credit_note_with_no_original_invoice_computes_vat_correctly(client):
    """Product Owner request: a Sales Return doesn't have to correspond to
    one whole invoice — this exercises the fully freeform case (no
    original_invoice_id at all, two lines that were never on any single
    invoice together), asserting VAT is computed per line and summed, not
    copied from anywhere."""
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    other_product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    resp = await client.post(
        "/api/v1/sales/invoices:return",
        headers=headers,
        json={
            "partner_id": partner_id,
            "reason": "Freeform multi-item return, no original invoice",
            "restock": False,
            "lines": [
                {"product_id": product_id, "qty": "3", "unit_price": "100.00", "tax_rate_id": tax_rate_id},
                {"product_id": other_product_id, "qty": "1", "unit_price": "250.00", "tax_rate_id": tax_rate_id},
            ],
        },
    )
    assert resp.status_code == 201
    body = resp.json()["invoice"]
    assert body["invoice_type"] == "credit_note"
    assert body["original_invoice_id"] is None
    # subtotal = 3*100 + 1*250 = 550; VAT 15% = 82.50; total = 632.50
    assert body["subtotal_amount"] == "550.00"
    assert body["tax_amount"] == "82.50"
    assert body["total_amount"] == "632.50"

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    assert rows["1200"]["total_debit"] == "0.0000"
    assert rows["1200"]["total_credit"] == "632.5000"
    assert rows["2200"]["total_debit"] == "82.5000"  # VAT payable reduced (credit note direction)


async def test_freeform_credit_note_with_optional_original_reference_uses_custom_lines(client):
    """The original invoice is given for traceability only — the return's
    own lines (different qty here) are what get billed, not a verbatim
    copy of the original invoice's lines."""
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    order_id = await _create_quotation_and_confirm(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    invoice_id = invoice_resp.json()["invoice"]["id"]  # original: 2 @ 1000.00 = 2300 total

    resp = await client.post(
        "/api/v1/sales/invoices:return",
        headers=headers,
        json={
            "partner_id": partner_id,
            "original_invoice_id": invoice_id,
            "reason": "Only 1 unit actually came back",
            "restock": False,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": tax_rate_id}],
        },
    )
    assert resp.status_code == 201
    body = resp.json()["invoice"]
    assert body["original_invoice_id"] == invoice_id
    # NOT the original's 2300 total — the freeform line's own 1150.
    assert body["total_amount"] == "1150.00"


async def test_freeform_credit_note_restocks_at_original_delivery_cost_when_product_matches(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)
    invoice_id, _ = await _sell_with_stock(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )

    resp = await client.post(
        "/api/v1/sales/invoices:return",
        headers=headers,
        json={
            "partner_id": partner_id,
            "original_invoice_id": invoice_id,
            "reason": "1 of the 2 sold units came back",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": tax_rate_id}],
        },
    )
    assert resp.status_code == 201

    moves = (
        await client.get("/api/v1/inventory/stock/moves", headers=headers, params={"product_id": product_id})
    ).json()
    return_moves = [m for m in moves if m["move_type"] == "return"]
    assert len(return_moves) == 1
    assert return_moves[0]["qty"] == "1.000000"
    assert return_moves[0]["unit_cost"] == "400.0000"  # exact original delivery cost, not recomputed


async def test_freeform_credit_note_restocks_at_average_cost_with_no_original_reference(client):
    """No original_invoice_id at all -> no delivery move to look the cost
    up from, so the restock falls back to the location's current
    moving-average cost."""
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True}
    )
    location_id = wh_resp.json()["default_location"]["id"]
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "500.00"},
    )

    resp = await client.post(
        "/api/v1/sales/invoices:return",
        headers=headers,
        json={
            "partner_id": partner_id,
            "reason": "Return with no invoice at all",
            "lines": [{"product_id": product_id, "qty": "2", "unit_price": "900.00", "tax_rate_id": tax_rate_id}],
        },
    )
    assert resp.status_code == 201

    moves = (
        await client.get("/api/v1/inventory/stock/moves", headers=headers, params={"product_id": product_id})
    ).json()
    return_moves = [m for m in moves if m["move_type"] == "return"]
    assert len(return_moves) == 1
    assert return_moves[0]["unit_cost"] == "500.0000"  # current average cost, the only basis available


async def test_list_invoices_filters_by_invoice_type_for_the_returns_screen(client):
    """P0-9 Owner follow-up: the dedicated Sales Returns screen needs to
    ask the list endpoint for exactly the credit notes, not fetch
    everything and filter client-side."""
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)
    invoice_id, _ = await _sell_with_stock(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )
    credit_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice_id}:credit-note", headers=headers, json={"reason": "Return"}
    )
    credit_note_id = credit_resp.json()["invoice"]["id"]

    returns_resp = await client.get(
        "/api/v1/sales/invoices", headers=headers, params={"invoice_type": "credit_note"}
    )
    assert returns_resp.status_code == 200
    returns_ids = {row["id"] for row in returns_resp.json()["items"]}
    assert returns_ids == {credit_note_id}  # the original invoice must NOT appear


# --- Product Owner request: edit a transaction before it's posted, with a
# "View Journal Entry" button on the screens that get one --------------


async def test_draft_quotation_can_be_edited(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    other_partner_id = await _create_partner(client, headers, is_b2b=False)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    create_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-03-01",
            "lines": [{"product_id": product_id, "qty": "2", "unit_price": "1000.00", "tax_rate_id": tax_rate_id}],
        },
    )
    quotation_id = create_resp.json()["id"]

    edit_resp = await client.put(
        f"/api/v1/sales/quotations/{quotation_id}",
        headers=headers,
        json={
            "partner_id": other_partner_id,
            "quote_date": "2026-03-05",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "500.00", "tax_rate_id": tax_rate_id}],
        },
    )
    assert edit_resp.status_code == 200
    edited = edit_resp.json()
    assert edited["partner_id"] == other_partner_id
    assert edited["quote_date"] == "2026-03-05"
    assert edited["total_amount"] == "500.00"  # not the original 2000.00

    detail = (await client.get(f"/api/v1/sales/quotations/{quotation_id}", headers=headers)).json()
    assert len(detail["lines"]) == 1
    assert detail["lines"][0]["qty"] == "1.000000"


async def test_confirmed_quotation_cannot_be_edited(client):
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    order_id_or_quotation = await _create_quotation_and_confirm(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )
    # _create_quotation_and_confirm returns the sales_order_id; re-fetch the
    # quotation itself via the list endpoint to get its own id.
    quotations = (await client.get("/api/v1/sales/quotations", headers=headers)).json()
    quotation_id = next(q["id"] for q in quotations if q["status"] == "confirmed")
    assert order_id_or_quotation  # sanity: an order really was created

    edit_resp = await client.put(
        f"/api/v1/sales/quotations/{quotation_id}",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-03-01",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1.00", "tax_rate_id": tax_rate_id}],
        },
    )
    assert edit_resp.status_code == 422
    assert "draft" in edit_resp.json()["detail"].lower()


async def test_invoice_and_credit_note_expose_journal_entry_id(client):
    """The 'View Journal Entry' button on the Sales Invoice detail screen
    depends on this field actually being in the API response."""
    _, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    order_id = await _create_quotation_and_confirm(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    invoice = invoice_resp.json()["invoice"]
    assert invoice["journal_entry_id"] is not None

    credit_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice['id']}:credit-note", headers=headers, json={"reason": "Return"}
    )
    assert credit_resp.json()["invoice"]["journal_entry_id"] is not None


async def test_sales_endpoints_require_permission(client):
    resp = await client.post("/api/v1/sales/quotations", json={})
    assert resp.status_code == 401


async def test_list_sales_orders(client):
    """UI/UX Professional pass: GET /sales/orders — Sales Orders had no
    list endpoint at all until this pass, so the frontend list screen had
    nowhere to fetch from."""
    company_id, headers = await _bootstrap_and_login(client)
    partner_id = await _create_partner(client, headers, is_b2b=True)
    product_id = await _create_product(client, headers)
    tax_rate_id = await _get_tax_rate_id(client, headers)

    order_id = await _create_quotation_and_confirm(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=tax_rate_id
    )

    list_resp = await client.get("/api/v1/sales/orders", headers=headers)
    assert list_resp.status_code == 200
    order_ids = [o["id"] for o in list_resp.json()]
    assert order_id in order_ids

    other_headers = (await _bootstrap_and_login(client))[1]
    other_list_resp = await client.get("/api/v1/sales/orders", headers=other_headers)
    assert order_id not in [o["id"] for o in other_list_resp.json()]
