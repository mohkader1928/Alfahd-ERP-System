"""Commercial Performance Stage 2B — Sales Representative transaction
attribution (Quotation -> SalesOrder -> SalesInvoice snapshot).

Covers exactly the approved Stage 2B scope: sales_rep_id copy-forward
through the Sales lifecycle, same pattern as warehouse_id/cost_center_id.
No credit-note attribution, no collection representative, no commission —
those are explicitly out of scope for this stage.
"""

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
    payload = {"name": "Stage2B Customer", "is_customer": True}
    payload.update(overrides)
    resp = await client.post("/api/v1/identity/partners", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_product(client, headers) -> str:
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Stage2B Product", "sales_price": "1000.00"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_quotation(client, headers, *, partner_id: str, product_id: str, sales_rep_id: str | None = None) -> dict:
    payload = {
        "partner_id": partner_id,
        "quote_date": "2026-06-01",
        "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
    }
    if sales_rep_id is not None:
        payload["sales_rep_id"] = sales_rep_id
    resp = await client.post("/api/v1/sales/quotations", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_explicit_sales_rep_id_persists_on_quotation_creation(client):
    """TEST 1."""
    _, headers = await _bootstrap_and_login(client, f"S2B-Create-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers)
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)

    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep["id"])
    assert quotation["sales_rep_id"] == rep["id"]

    reloaded = (await client.get(f"/api/v1/sales/quotations/{quotation['id']}", headers=headers)).json()
    assert reloaded["quotation"]["sales_rep_id"] == rep["id"]


async def test_explicit_selection_is_never_silently_overridden_by_partner_default(client):
    """TEST 2: the backend never re-reads Partner.default_sales_rep_id —
    an explicitly submitted sales_rep_id (deliberately different from the
    partner's own default) is what actually persists."""
    _, headers = await _bootstrap_and_login(client, f"S2B-Override-{unique_vat()[:6]}")
    rep_default = await _create_sales_rep(client, headers, name="Ahmed", code="REP-DEFAULT")
    rep_override = await _create_sales_rep(client, headers, name="Mohamed", code="REP-OVERRIDE")
    partner_id = await _create_partner(client, headers, default_sales_rep_id=rep_default["id"])
    product_id = await _create_product(client, headers)

    quotation = await _create_quotation(
        client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep_override["id"]
    )
    assert quotation["sales_rep_id"] == rep_override["id"]
    assert quotation["sales_rep_id"] != rep_default["id"]


async def test_quotation_sales_rep_copies_to_sales_order_on_confirm(client):
    """TEST 3."""
    _, headers = await _bootstrap_and_login(client, f"S2B-Confirm-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers)
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)
    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep["id"])

    order = (await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)).json()
    assert order["sales_rep_id"] == rep["id"]


async def test_sales_order_sales_rep_copies_to_invoice_on_issue(client):
    """TEST 4."""
    _, headers = await _bootstrap_and_login(client, f"S2B-Issue-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers)
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)
    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep["id"])
    order = (await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)).json()

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order['id']}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text
    assert invoice_resp.json()["invoice"]["sales_rep_id"] == rep["id"]


async def test_partner_default_change_does_not_alter_existing_quotation(client):
    """TEST 5."""
    _, headers = await _bootstrap_and_login(client, f"S2B-Hist-Quote-{unique_vat()[:6]}")
    rep_ahmed = await _create_sales_rep(client, headers, name="Ahmed", code="REP-JAN")
    rep_mohamed = await _create_sales_rep(client, headers, name="Mohamed", code="REP-MAR")
    partner_id = await _create_partner(client, headers, default_sales_rep_id=rep_ahmed["id"])
    product_id = await _create_product(client, headers)

    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep_ahmed["id"])

    # Reassign the customer's default rep later.
    update_resp = await client.patch(
        f"/api/v1/identity/partners/{partner_id}",
        headers=headers,
        json={"name": "Stage2B Customer", "is_customer": True, "default_sales_rep_id": rep_mohamed["id"]},
    )
    assert update_resp.status_code == 200, update_resp.text

    reloaded_quotation = (await client.get(f"/api/v1/sales/quotations/{quotation['id']}", headers=headers)).json()
    assert reloaded_quotation["quotation"]["sales_rep_id"] == rep_ahmed["id"]


async def test_partner_default_change_does_not_alter_existing_sales_order(client):
    """TEST 6."""
    _, headers = await _bootstrap_and_login(client, f"S2B-Hist-Order-{unique_vat()[:6]}")
    rep_ahmed = await _create_sales_rep(client, headers, name="Ahmed", code="REP-JAN2")
    rep_mohamed = await _create_sales_rep(client, headers, name="Mohamed", code="REP-MAR2")
    partner_id = await _create_partner(client, headers, default_sales_rep_id=rep_ahmed["id"])
    product_id = await _create_product(client, headers)
    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep_ahmed["id"])
    order = (await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)).json()

    await client.patch(
        f"/api/v1/identity/partners/{partner_id}",
        headers=headers,
        json={"name": "Stage2B Customer", "is_customer": True, "default_sales_rep_id": rep_mohamed["id"]},
    )

    reloaded_order = (await client.get(f"/api/v1/sales/orders/{order['id']}", headers=headers)).json()
    assert reloaded_order["order"]["sales_rep_id"] == rep_ahmed["id"]


async def test_partner_default_change_does_not_alter_existing_invoice(client):
    """TEST 7."""
    _, headers = await _bootstrap_and_login(client, f"S2B-Hist-Invoice-{unique_vat()[:6]}")
    rep_ahmed = await _create_sales_rep(client, headers, name="Ahmed", code="REP-JAN3")
    rep_mohamed = await _create_sales_rep(client, headers, name="Mohamed", code="REP-MAR3")
    partner_id = await _create_partner(client, headers, default_sales_rep_id=rep_ahmed["id"])
    product_id = await _create_product(client, headers)
    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep_ahmed["id"])
    order = (await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)).json()
    invoice = (await client.post(f"/api/v1/sales/orders/{order['id']}:invoice", headers=headers)).json()["invoice"]

    await client.patch(
        f"/api/v1/identity/partners/{partner_id}",
        headers=headers,
        json={"name": "Stage2B Customer", "is_customer": True, "default_sales_rep_id": rep_mohamed["id"]},
    )

    reloaded_invoice = (await client.get(f"/api/v1/sales/invoices/{invoice['id']}", headers=headers)).json()
    assert reloaded_invoice["invoice"]["sales_rep_id"] == rep_ahmed["id"]


async def test_cross_company_sales_rep_assignment_is_rejected_on_quotation(client):
    """TEST 8 (quotation create)."""
    _, headers_a = await _bootstrap_and_login(client, f"S2B-CrossA-{unique_vat()[:6]}")
    _, headers_b = await _bootstrap_and_login(client, f"S2B-CrossB-{unique_vat()[:6]}")
    rep_in_b = await _create_sales_rep(client, headers_b, code="REP-B-ONLY")
    partner_id = await _create_partner(client, headers_a)
    product_id = await _create_product(client, headers_a)

    resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers_a,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "sales_rep_id": rep_in_b["id"],
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert resp.status_code == 422, resp.text


async def test_cross_company_sales_rep_assignment_is_rejected_on_order_update(client):
    """TEST 8 (order update path)."""
    _, headers_a = await _bootstrap_and_login(client, f"S2B-CrossOrderA-{unique_vat()[:6]}")
    _, headers_b = await _bootstrap_and_login(client, f"S2B-CrossOrderB-{unique_vat()[:6]}")
    rep_in_b = await _create_sales_rep(client, headers_b, code="REP-B-ORDER")
    partner_id = await _create_partner(client, headers_a)
    product_id = await _create_product(client, headers_a)
    quotation = await _create_quotation(client, headers_a, partner_id=partner_id, product_id=product_id)
    order = (await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers_a)).json()

    resp = await client.put(
        f"/api/v1/sales/orders/{order['id']}",
        headers=headers_a,
        json={
            "partner_id": partner_id,
            "order_date": "2026-06-01",
            "sales_rep_id": rep_in_b["id"],
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert resp.status_code == 422, resp.text


async def test_customer_with_no_default_rep_completes_full_workflow(client):
    """TEST 9: unattributed (NULL) throughout is a normal, working state."""
    _, headers = await _bootstrap_and_login(client, f"S2B-NoRep-{unique_vat()[:6]}")
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)

    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id)
    assert quotation["sales_rep_id"] is None
    order = (await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)).json()
    assert order["sales_rep_id"] is None
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order['id']}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text
    assert invoice_resp.json()["invoice"]["sales_rep_id"] is None
    assert invoice_resp.json()["invoice"]["total_amount"] == "1150.00"


async def test_full_workflow_with_rep_preserves_same_rep_end_to_end(client):
    """TEST 10."""
    _, headers = await _bootstrap_and_login(client, f"S2B-EndToEnd-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers)
    partner_id = await _create_partner(client, headers, default_sales_rep_id=rep["id"])
    product_id = await _create_product(client, headers)

    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep["id"])
    order = (await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)).json()
    invoice = (await client.post(f"/api/v1/sales/orders/{order['id']}:invoice", headers=headers)).json()["invoice"]

    assert quotation["sales_rep_id"] == rep["id"]
    assert order["sales_rep_id"] == rep["id"]
    assert invoice["sales_rep_id"] == rep["id"]


async def test_quotation_sales_rep_editable_while_draft(client):
    """Edit-window test: sales_rep_id can be changed via update_quotation
    while the quotation is still draft, mirroring warehouse_id/cost_center_id."""
    _, headers = await _bootstrap_and_login(client, f"S2B-EditWindow-{unique_vat()[:6]}")
    rep_a = await _create_sales_rep(client, headers, name="Ahmed", code="REP-EDIT-A")
    rep_b = await _create_sales_rep(client, headers, name="Mohamed", code="REP-EDIT-B")
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)
    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep_a["id"])

    update_resp = await client.put(
        f"/api/v1/sales/quotations/{quotation['id']}",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "sales_rep_id": rep_b["id"],
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["sales_rep_id"] == rep_b["id"]


async def test_sales_order_sales_rep_editable_before_invoicing(client):
    """Edit-window test on the SalesOrder side, mirroring update_order's
    existing nothing-invoiced-yet guard."""
    _, headers = await _bootstrap_and_login(client, f"S2B-OrderEdit-{unique_vat()[:6]}")
    rep_a = await _create_sales_rep(client, headers, name="Ahmed", code="REP-OE-A")
    rep_b = await _create_sales_rep(client, headers, name="Mohamed", code="REP-OE-B")
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)
    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id, sales_rep_id=rep_a["id"])
    order = (await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)).json()

    update_resp = await client.put(
        f"/api/v1/sales/orders/{order['id']}",
        headers=headers,
        json={
            "partner_id": partner_id,
            "order_date": "2026-06-01",
            "sales_rep_id": rep_b["id"],
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["sales_rep_id"] == rep_b["id"]


async def test_legacy_null_sales_rep_reads_correctly(client):
    """TEST 11: an existing quotation created before/without sales_rep_id
    reads back cleanly with sales_rep_id: null — no invented attribution."""
    _, headers = await _bootstrap_and_login(client, f"S2B-Legacy-{unique_vat()[:6]}")
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)
    quotation = await _create_quotation(client, headers, partner_id=partner_id, product_id=product_id)
    assert quotation["sales_rep_id"] is None

    reloaded = (await client.get(f"/api/v1/sales/quotations/{quotation['id']}", headers=headers)).json()
    assert reloaded["quotation"]["sales_rep_id"] is None


async def test_schema_backward_compatible_without_sales_rep_field(client):
    """Payload omitting sales_rep_id entirely (old-shape client) still
    works — API backward compatibility."""
    _, headers = await _bootstrap_and_login(client, f"S2B-Compat-{unique_vat()[:6]}")
    partner_id = await _create_partner(client, headers)
    product_id = await _create_product(client, headers)
    resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["sales_rep_id"] is None
