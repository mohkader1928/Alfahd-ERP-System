"""Commercial Performance Stage 1 — customer/vendor credit management.

Covers exactly the approved Stage 1 scope: structured credit_limit/
credit_days/vendor_credit_days on Partner, and automatic due_date
population on newly issued SalesInvoice/VendorBill rows. No commission,
no sales representative, no approval workflow, no accounting/VAT change —
those are explicitly out of scope for this stage.
"""

from datetime import date, timedelta
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


async def _create_product(client, headers) -> str:
    resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Credit Mgmt Product", "sales_price": "1000.00"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _issue_customer_invoice(client, headers, *, partner_id: str, product_id: str, quote_date: str) -> dict:
    quote = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": quote_date,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "1000.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert quote.status_code == 201, quote.text
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text
    return invoice_resp.json()["invoice"]


async def _register_vendor_bill(client, headers, *, vendor_id: str, product_id: str) -> dict:
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "Credit Mgmt WH", "is_default": True})
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "10", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert po_resp.status_code == 201, po_resp.text
    order_id = po_resp.json()["id"]
    assert (await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)).status_code == 200

    po_line_id = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()["lines"][0]["id"]
    receipt_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "10"}]},
    )
    assert receipt_resp.status_code == 201, receipt_resp.text

    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "REF-1", "lines": [{"purchase_order_line_id": po_line_id, "qty": "10", "unit_price": "20.00"}]},
    )
    assert bill_resp.status_code == 201, bill_resp.text
    return bill_resp.json()


async def test_partner_credit_fields_save_and_reload(client):
    """TEST 1: customer credit_limit/credit_days and vendor vendor_credit_days
    save and reload correctly, and updating them persists the new values."""
    _, headers = await _bootstrap_and_login(client, f"Credit-Save-{unique_vat()[:6]}")

    create_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={
            "name": "Credit Customer",
            "is_customer": True,
            "is_vendor": True,
            "credit_limit": "50000.00",
            "credit_days": 30,
            "vendor_credit_days": 45,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    partner = create_resp.json()
    assert Decimal(partner["credit_limit"]) == Decimal("50000.00")
    assert partner["credit_days"] == 30
    assert partner["vendor_credit_days"] == 45
    partner_id = partner["id"]

    reloaded = (await client.get(f"/api/v1/identity/partners/{partner_id}", headers=headers)).json()
    assert Decimal(reloaded["credit_limit"]) == Decimal("50000.00")
    assert reloaded["credit_days"] == 30
    assert reloaded["vendor_credit_days"] == 45

    update_resp = await client.patch(
        f"/api/v1/identity/partners/{partner_id}",
        headers=headers,
        json={
            "name": "Credit Customer",
            "is_customer": True,
            "is_vendor": True,
            "credit_limit": "75000.50",
            "credit_days": 60,
            "vendor_credit_days": 90,
        },
    )
    assert update_resp.status_code == 200, update_resp.text
    assert Decimal(update_resp.json()["credit_limit"]) == Decimal("75000.50")
    assert update_resp.json()["credit_days"] == 60
    assert update_resp.json()["vendor_credit_days"] == 90

    reloaded2 = (await client.get(f"/api/v1/identity/partners/{partner_id}", headers=headers)).json()
    assert Decimal(reloaded2["credit_limit"]) == Decimal("75000.50")
    assert reloaded2["credit_days"] == 60
    assert reloaded2["vendor_credit_days"] == 90


async def test_partner_credit_fields_default_to_null(client):
    """API backward compatibility: a partner created without any of the
    new fields keeps working exactly as before, with all three NULL."""
    _, headers = await _bootstrap_and_login(client, f"Credit-Null-{unique_vat()[:6]}")
    resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Plain Partner", "is_customer": True}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["credit_limit"] is None
    assert body["credit_days"] is None
    assert body["vendor_credit_days"] is None


async def test_customer_invoice_due_date_calculated_from_credit_days(client):
    """TEST 2: due_date = invoice_date + partner.credit_days."""
    _, headers = await _bootstrap_and_login(client, f"Credit-Due-{unique_vat()[:6]}")
    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "Net30 Customer", "is_customer": True, "credit_days": 30},
    )
    partner_id = partner_resp.json()["id"]
    product_id = await _create_product(client, headers)

    invoice = await _issue_customer_invoice(client, headers, partner_id=partner_id, product_id=product_id, quote_date="2026-06-01")
    assert invoice["invoice_date"] == "2026-06-01"
    assert invoice["due_date"] == (date(2026, 6, 1) + timedelta(days=30)).isoformat()


async def test_customer_invoice_due_date_falls_back_to_invoice_date_when_no_credit_days(client):
    """TEST 3: no credit period configured -> due_date == invoice_date."""
    _, headers = await _bootstrap_and_login(client, f"Credit-Fallback-{unique_vat()[:6]}")
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "No-Terms Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    product_id = await _create_product(client, headers)

    invoice = await _issue_customer_invoice(client, headers, partner_id=partner_id, product_id=product_id, quote_date="2026-06-15")
    assert invoice["invoice_date"] == "2026-06-15"
    assert invoice["due_date"] == "2026-06-15"


async def test_vendor_bill_due_date_calculated_from_vendor_credit_days(client):
    """TEST 4: due_date = bill_date + partner.vendor_credit_days."""
    _, headers = await _bootstrap_and_login(client, f"VendorCredit-Due-{unique_vat()[:6]}")
    vendor_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "Net45 Vendor", "is_vendor": True, "vendor_credit_days": 45},
    )
    vendor_id = vendor_resp.json()["id"]
    product_id = await _create_product(client, headers)

    bill = await _register_vendor_bill(client, headers, vendor_id=vendor_id, product_id=product_id)
    assert bill["bill_date"] == date.today().isoformat()
    assert bill["due_date"] == (date.today() + timedelta(days=45)).isoformat()


async def test_vendor_bill_due_date_falls_back_to_bill_date_when_no_vendor_credit_days(client):
    """TEST 5: no vendor credit period configured -> due_date == bill_date."""
    _, headers = await _bootstrap_and_login(client, f"VendorCredit-Fallback-{unique_vat()[:6]}")
    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "No-Terms Vendor", "is_vendor": True}
    )
    vendor_id = vendor_resp.json()["id"]
    product_id = await _create_product(client, headers)

    bill = await _register_vendor_bill(client, headers, vendor_id=vendor_id, product_id=product_id)
    assert bill["bill_date"] == date.today().isoformat()
    assert bill["due_date"] == date.today().isoformat()


async def test_historical_invoice_due_date_unaffected_by_later_credit_change(client):
    """TEST 6: an invoice issued before a customer's credit_days was set
    (or with a different value) must keep its own due_date forever —
    changing the partner's credit terms later must not rewrite history."""
    _, headers = await _bootstrap_and_login(client, f"Credit-Historical-{unique_vat()[:6]}")
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Evolving Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    product_id = await _create_product(client, headers)

    old_invoice = await _issue_customer_invoice(
        client, headers, partner_id=partner_id, product_id=product_id, quote_date="2026-03-01"
    )
    assert old_invoice["due_date"] == "2026-03-01"  # no credit_days yet -> falls back to invoice_date

    update_resp = await client.patch(
        f"/api/v1/identity/partners/{partner_id}",
        headers=headers,
        json={"name": "Evolving Customer", "is_customer": True, "credit_days": 15},
    )
    assert update_resp.status_code == 200, update_resp.text

    new_invoice = await _issue_customer_invoice(
        client, headers, partner_id=partner_id, product_id=product_id, quote_date="2026-07-01"
    )
    assert new_invoice["due_date"] == (date(2026, 7, 1) + timedelta(days=15)).isoformat()

    # The historical invoice must be completely unaffected by the later change.
    reloaded_old = await client.get(f"/api/v1/sales/invoices/{old_invoice['id']}", headers=headers)
    assert reloaded_old.status_code == 200
    assert reloaded_old.json()["invoice"]["due_date"] == "2026-03-01"


async def test_partner_credit_fields_isolated_across_companies(client):
    """TEST 7: multi-company isolation — a partner's credit fields created
    in one company must not be readable or writable via another company's
    context (RLS company_isolation, unchanged by this stage)."""
    _, headers_a = await _bootstrap_and_login(client, f"Credit-Iso-A-{unique_vat()[:6]}")
    _, headers_b = await _bootstrap_and_login(client, f"Credit-Iso-B-{unique_vat()[:6]}")

    create_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers_a,
        json={"name": "Company A Customer", "is_customer": True, "credit_limit": "10000.00", "credit_days": 30},
    )
    partner_id = create_resp.json()["id"]

    cross_get = await client.get(f"/api/v1/identity/partners/{partner_id}", headers=headers_b)
    assert cross_get.status_code == 404

    cross_update = await client.patch(
        f"/api/v1/identity/partners/{partner_id}",
        headers=headers_b,
        json={"name": "Hijacked", "is_customer": True, "credit_limit": "999999.00"},
    )
    assert cross_update.status_code == 404

    # Still fully intact and unchanged under its own company's context.
    still_valid = await client.get(f"/api/v1/identity/partners/{partner_id}", headers=headers_a)
    assert still_valid.status_code == 200
    assert still_valid.json()["credit_limit"] == "10000.0000"
