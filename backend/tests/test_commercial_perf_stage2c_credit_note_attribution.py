"""Commercial Performance Stage 2C — Sales Representative attribution on
Credit Notes / Sales Returns.

Covers exactly the approved Stage 2C scope: issue_credit_note inherits
sales_rep_id from the original invoice; issue_credit_note_for_lines
inherits from the original invoice when referenced, else defaults from
Partner.default_sales_rep_id at creation time (the one documented
exception — there is no original to inherit from in the genuinely
freeform case). No collection representative, no commission — those are
explicitly out of scope for this stage.
"""

from decimal import Decimal

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
    assert boot_resp.status_code == 201, boot_resp.text
    company_id = boot_resp.json()["company_id"]
    branch_id = boot_resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, headers


async def _create_sales_rep(client, headers, *, name: str = "Ahmed", code: str = "REP001") -> dict:
    resp = await client.post("/api/v1/identity/sales-representatives", headers=headers, json={"name": name, "code": code})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_partner(client, headers, **overrides) -> str:
    payload = {"name": "Stage2C Customer", "is_customer": True}
    payload.update(overrides)
    resp = await client.post("/api/v1/identity/partners", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_product(client, headers) -> str:
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Stage2C Product", "sales_price": "1000.00"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _issue_invoice(client, headers, *, partner_id: str, product_id: str, sales_rep_id: str | None = None) -> dict:
    quote_payload = {
        "partner_id": partner_id,
        "quote_date": "2026-06-01",
        "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
    }
    if sales_rep_id is not None:
        quote_payload["sales_rep_id"] = sales_rep_id
    quote = await client.post("/api/v1/sales/quotations", headers=headers, json=quote_payload)
    assert quote.status_code == 201, quote.text
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text
    return invoice_resp.json()["invoice"]


async def test_credit_note_inherits_representative_from_original_invoice(client):
    """TEST: issue_credit_note (single-invoice path)."""
    _, headers = await _bootstrap_and_login(client, f"S2C-CN-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers)
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)
    invoice = await _issue_invoice(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep["id"])

    credit_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice['id']}:credit-note",
        headers=headers,
        json={"reason": "Stage 2C — full return", "restock": False},
    )
    assert credit_resp.status_code == 201, credit_resp.text
    assert credit_resp.json()["invoice"]["sales_rep_id"] == rep["id"]


async def test_freeform_credit_note_with_original_invoice_inherits_representative(client):
    """TEST: issue_credit_note_for_lines with original_invoice_id set."""
    _, headers = await _bootstrap_and_login(client, f"S2C-FreeCN-Orig-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers)
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)
    invoice = await _issue_invoice(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep["id"])

    resp = await client.post(
        "/api/v1/sales/invoices:return",
        headers=headers,
        json={
            "partner_id": partner_id,
            "original_invoice_id": invoice["id"],
            "reason": "Stage 2C — freeform with original",
            "restock": False,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["invoice"]["sales_rep_id"] == rep["id"]


async def test_freeform_credit_note_without_original_defaults_from_customer(client):
    """TEST: issue_credit_note_for_lines with NO original_invoice_id —
    defaults from the customer's CURRENT default_sales_rep_id at the
    moment of creation, per the approved design's one documented
    exception."""
    _, headers = await _bootstrap_and_login(client, f"S2C-FreeCN-NoOrig-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers)
    partner_id = await _create_partner(client, headers, default_sales_rep_id=rep["id"])
    product_id = await _create_product(client, headers)

    resp = await client.post(
        "/api/v1/sales/invoices:return",
        headers=headers,
        json={
            "partner_id": partner_id,
            "reason": "Stage 2C — genuinely freeform, no original",
            "restock": False,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["invoice"]["original_invoice_id"] is None
    assert resp.json()["invoice"]["sales_rep_id"] == rep["id"]


async def test_freeform_credit_note_without_original_or_default_stays_unattributed(client):
    """A customer with no default rep at all produces a genuinely
    unattributed freeform return — not an error, not an invented value."""
    _, headers = await _bootstrap_and_login(client, f"S2C-FreeCN-NoRep-{unique_vat()[:6]}")
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)

    resp = await client.post(
        "/api/v1/sales/invoices:return",
        headers=headers,
        json={
            "partner_id": partner_id,
            "reason": "Stage 2C — no rep configured at all",
            "restock": False,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["invoice"]["sales_rep_id"] is None


async def test_changing_customer_rep_later_does_not_alter_old_credit_note(client):
    """TEST: historical accuracy — reassigning the customer's default rep
    after a credit note already exists must not touch it, for both the
    original-invoice-inherited case and the freeform-defaulted case."""
    _, headers = await _bootstrap_and_login(client, f"S2C-Hist-{unique_vat()[:6]}")
    rep_ahmed = await _create_sales_rep(client, headers, name="Ahmed", code="REP-JAN")
    rep_mohamed = await _create_sales_rep(client, headers, name="Mohamed", code="REP-MAR")
    partner_id = await _create_partner(client, headers, default_sales_rep_id=rep_ahmed["id"])
    product_id = await _create_product(client, headers)
    invoice = await _issue_invoice(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep_ahmed["id"])

    credit_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice['id']}:credit-note",
        headers=headers,
        json={"reason": "Before reassignment", "restock": False},
    )
    credit_note_id = credit_resp.json()["invoice"]["id"]

    freeform_resp = await client.post(
        "/api/v1/sales/invoices:return",
        headers=headers,
        json={
            "partner_id": partner_id,
            "reason": "Freeform before reassignment",
            "restock": False,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    freeform_credit_note_id = freeform_resp.json()["invoice"]["id"]

    # Reassign the customer's default rep.
    await client.patch(
        f"/api/v1/identity/partners/{partner_id}",
        headers=headers,
        json={"name": "Stage2C Customer", "is_customer": True, "default_sales_rep_id": rep_mohamed["id"]},
    )

    reloaded_credit_note = (await client.get(f"/api/v1/sales/invoices/{credit_note_id}", headers=headers)).json()
    assert reloaded_credit_note["invoice"]["sales_rep_id"] == rep_ahmed["id"]

    reloaded_freeform = (await client.get(f"/api/v1/sales/invoices/{freeform_credit_note_id}", headers=headers)).json()
    assert reloaded_freeform["invoice"]["sales_rep_id"] == rep_ahmed["id"]


async def test_credit_note_workflow_accounting_and_restock_unaffected(client):
    """Regression: the full invoice -> credit note workflow, including
    accounting reversal and restock, is completely unaffected by the
    sales_rep_id attribution added in this stage."""
    _, headers = await _bootstrap_and_login(client, f"S2C-Regress-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers)
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)
    invoice = await _issue_invoice(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep["id"])

    credit_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice['id']}:credit-note",
        headers=headers,
        json={"reason": "Regression check", "restock": True},
    )
    assert credit_resp.status_code == 201, credit_resp.text
    credit_note = credit_resp.json()["invoice"]
    assert Decimal(credit_note["total_amount"]) == Decimal(invoice["total_amount"])

    trial_balance = await client.get(
        "/api/v1/accounting/reports/trial-balance",
        headers=headers,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    rows = {row["account_code"]: row for row in trial_balance.json()}
    # Invoice + credit note should net AR to zero.
    assert rows["1200"]["total_debit"] == rows["1200"]["total_credit"]
