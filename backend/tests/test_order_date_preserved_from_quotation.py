"""Regression test for a real, reported bug: confirming a quotation into a
sales order silently discarded the quotation's own date and stamped
`date.today()` instead — so a quotation deliberately dated in the past (or
future) lost that date the moment it became an order, with no indication
to the user. Reported directly by the Owner ("entered invoices for January,
dashboard never reflected it") while testing; traced to this line, not a
dashboard bug.

Also locks in that `invoice_date` is present on the API response at all —
it was silently absent from `SalesInvoiceOut`, so the frontend had no way
to ever show it, which is part of why the discarded date went unnoticed.
"""

from datetime import date

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Order Date Holding",
        "company_legal_name": "Order Date Trading Co.",
        "company_legal_name_ar": "Order Date Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Order Date Admin",
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


async def test_confirming_quotation_preserves_its_own_date(client):
    _, headers = await _bootstrap_and_login(client)

    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Jan Customer", "is_customer": True}
    )
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"JAN-{unique_vat()[:8]}", "name": "January Widget", "sales_price": "500.00"},
    )

    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_resp.json()["id"],
            "quote_date": "2026-01-15",
            "lines": [
                {
                    "product_id": product_resp.json()["id"],
                    "qty": "1",
                    "unit_price": "500.00",
                    "tax_rate_id": TAX_RATE_PLACEHOLDER,
                }
            ],
        },
    )
    assert quote_resp.status_code == 201
    assert quote_resp.json()["quote_date"] == "2026-01-15"

    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)
    assert confirm_resp.status_code == 200
    # This is the bug: it used to always be date.today() here, silently
    # discarding "2026-01-15" the moment the quotation became an order.
    assert confirm_resp.json()["order_date"] == "2026-01-15"


async def test_invoice_response_exposes_its_own_invoice_date(client):
    _, headers = await _bootstrap_and_login(client)

    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Invoice Date Customer", "is_customer": True}
    )
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"IDT-{unique_vat()[:8]}", "name": "Invoice Date Widget", "sales_price": "200.00"},
    )
    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_resp.json()["id"],
            "quote_date": "2026-01-15",
            "lines": [
                {
                    "product_id": product_resp.json()["id"],
                    "qty": "1",
                    "unit_price": "200.00",
                    "tax_rate_id": TAX_RATE_PLACEHOLDER,
                }
            ],
        },
    )
    confirm_resp = await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)
    order_id = confirm_resp.json()["id"]

    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    invoice = invoice_resp.json()["invoice"]
    # Previously absent from SalesInvoiceOut entirely — the frontend had no
    # field to ever display, regardless of what the value was. Issuance date
    # is deliberately real-time (ZATCA issue-date requirement), unlike the
    # order date above, so this asserts today's date, not the quote date.
    assert invoice["invoice_date"] == date.today().isoformat()
