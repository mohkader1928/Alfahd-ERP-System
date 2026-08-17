"""Owner request: attribute Sales revenue to a specific Cost Center. A
cost_center_id chosen once on the Quotation carries forward through
SalesOrder and into the SalesInvoice, ending up on the revenue line of
the journal entry the invoice auto-posts -- the same header-level,
copy-forward-once shape as warehouse_id (see test_warehouse_stock_balance.py)."""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client, label="SCC"):
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
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, headers


async def _create_cost_center(client, headers, name="Retail") -> str:
    resp = await client.post("/api/v1/accounting/cost-centers", headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_customer(client, headers, name="Customer") -> str:
    resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": name, "is_customer": True}
    )
    return resp.json()["id"]


async def _create_product(client, headers, name="Product") -> str:
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SCC-{unique_vat()[:8]}", "name": name, "sales_price": "50.00"},
    )
    return resp.json()["id"]


async def _create_quotation(client, headers, *, customer_id, product_id, cost_center_id=None) -> dict:
    payload = {
        "partner_id": customer_id,
        "quote_date": "2026-06-01",
        "lines": [{"product_id": product_id, "qty": "2", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
    }
    if cost_center_id is not None:
        payload["cost_center_id"] = cost_center_id
    resp = await client.post("/api/v1/sales/quotations", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _get_journal_entry(client, headers, journal_entry_id) -> dict:
    resp = await client.get(f"/api/v1/accounting/journal-entries/{journal_entry_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_quotation_cost_center_carries_through_to_invoice_and_journal_entry(client):
    _, headers = await _bootstrap_and_login(client, "Carry")
    cc_id = await _create_cost_center(client, headers, "Store 1")
    customer_id = await _create_customer(client, headers)
    product_id = await _create_product(client, headers)

    quotation = await _create_quotation(client, headers, customer_id=customer_id, product_id=product_id, cost_center_id=cc_id)
    assert quotation["cost_center_id"] == cc_id

    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)
    assert confirm_resp.status_code == 200, confirm_resp.text
    order = confirm_resp.json()
    assert order["cost_center_id"] == cc_id

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order['id']}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text
    invoice = invoice_resp.json()["invoice"]
    assert invoice["cost_center_id"] == cc_id

    entry = await _get_journal_entry(client, headers, invoice["journal_entry_id"])
    lines = entry["lines"]
    # Exactly one line (the revenue line) carries the cost center -- AR
    # and VAT are balance-sheet lines, not meaningfully attributable to a
    # cost center, so the service never sets it there.
    lines_with_cc = [line for line in lines if line["cost_center_id"] is not None]
    assert len(lines_with_cc) == 1
    assert lines_with_cc[0]["cost_center_id"] == cc_id
    assert lines_with_cc[0]["credit"] != "0.0000"  # it's the credit-side revenue line


async def test_quotation_without_cost_center_posts_normally(client):
    """Backward compatibility: cost_center_id is optional -- omitting it
    keeps working exactly as before this feature, with no cost center on
    any journal entry line."""
    _, headers = await _bootstrap_and_login(client, "NoCc")
    customer_id = await _create_customer(client, headers)
    product_id = await _create_product(client, headers)

    quotation = await _create_quotation(client, headers, customer_id=customer_id, product_id=product_id)
    assert quotation["cost_center_id"] is None

    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)
    order = confirm_resp.json()
    assert order["cost_center_id"] is None

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order['id']}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text
    invoice = invoice_resp.json()["invoice"]
    assert invoice["cost_center_id"] is None

    entry = await _get_journal_entry(client, headers, invoice["journal_entry_id"])
    assert all(line["cost_center_id"] is None for line in entry["lines"])


async def test_sales_order_edit_can_change_cost_center_before_invoicing(client):
    _, headers = await _bootstrap_and_login(client, "EditCc")
    cc_a = await _create_cost_center(client, headers, "Store A")
    cc_b = await _create_cost_center(client, headers, "Store B")
    customer_id = await _create_customer(client, headers)
    product_id = await _create_product(client, headers)

    quotation = await _create_quotation(client, headers, customer_id=customer_id, product_id=product_id, cost_center_id=cc_a)
    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers)
    order = confirm_resp.json()
    assert order["cost_center_id"] == cc_a

    update_resp = await client.put(
        f"/api/v1/sales/orders/{order['id']}",
        headers=headers,
        json={
            "partner_id": customer_id,
            "order_date": "2026-06-01",
            "cost_center_id": cc_b,
            "lines": [{"product_id": product_id, "qty": "2", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["cost_center_id"] == cc_b

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order['id']}:invoice", headers=headers)
    assert invoice_resp.json()["invoice"]["cost_center_id"] == cc_b


async def test_invoice_issuance_rejects_cross_company_cost_center(client):
    """A cost_center_id is only threaded through, never validated, at the
    Quotation/SalesOrder stage (same as warehouse_id) -- but issuing the
    invoice runs it through the real JournalEntryService validation, which
    must reject a cost center that belongs to a different company."""
    _, headers_a = await _bootstrap_and_login(client, "CrossA")
    _, headers_b = await _bootstrap_and_login(client, "CrossB")
    cc_b = await _create_cost_center(client, headers_b, "Belongs To B")

    customer_id = await _create_customer(client, headers_a)
    product_id = await _create_product(client, headers_a)
    quotation = await _create_quotation(client, headers_a, customer_id=customer_id, product_id=product_id, cost_center_id=cc_b)

    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quotation['id']}:confirm", headers=headers_a)
    order = confirm_resp.json()

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order['id']}:invoice", headers=headers_a)
    assert invoice_resp.status_code == 422
    assert "not found in this company" in invoice_resp.json()["detail"]
