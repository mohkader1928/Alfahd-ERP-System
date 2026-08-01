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


async def test_sales_endpoints_require_permission(client):
    resp = await client.post("/api/v1/sales/quotations", json={})
    assert resp.status_code == 401
