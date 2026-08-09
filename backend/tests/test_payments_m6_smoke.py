"""Integration smoke test for Phase 17D — Payments.

Amount comparisons use `Decimal(...) ==` rather than raw string equality:
the API echoes amounts with the DB's `Numeric(18,4)` precision (e.g.
"230.0000"), which is numerically but not string-identical to the
2-decimal-place amount the client sent (e.g. "230.00").

Exercises: customer payment (full + partial) against a sales invoice,
vendor payment against a vendor bill, overpayment rejection, cross-partner
allocation rejection, and cross-company RLS isolation — all through the
real HTTP API against the real dockerized Postgres, same pattern as every
other test in this suite.
"""

import asyncio
from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client, label: str = "Pay Test"):
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


async def _cash_account_id(client, headers) -> str:
    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    return next(a["id"] for a in accounts if a["code"] == "1100")


async def _issue_customer_invoice(client, headers, *, total_qty="2", unit_price="100.00") -> tuple[str, str, str]:
    """Returns (invoice_id, invoice_total, partner_id) for a simplified
    (no vat_number) B2C invoice — synchronous clearance isn't needed here."""
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Cash Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]

    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Widget", "sales_price": unit_price},
    )
    product_id = product_resp.json()["id"]

    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": total_qty, "unit_price": unit_price, "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    quotation_id = quote_resp.json()["id"]
    order_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    order_id = order_resp.json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    invoice = invoice_resp.json()["invoice"]
    return invoice["id"], invoice["total_amount"], partner_id


async def _issue_vendor_bill(client, headers, *, qty="5", unit_price="20.00") -> tuple[str, str, str]:
    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Steel Supplier LLC", "is_vendor": True}
    )
    vendor_id = vendor_resp.json()["id"]

    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Steel Rod", "sales_price": "50.00"},
    )
    product_id = product_resp.json()["id"]

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": qty, "unit_price": unit_price, "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": qty}]},
    )
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": qty, "unit_price": unit_price}]},
    )
    assert bill_resp.status_code == 201
    bill = bill_resp.json()
    return bill["id"], bill["total_amount"], vendor_id


async def test_customer_payment_full_allocation_posts_journal_entry(client):
    _, headers = await _bootstrap_and_login(client)
    invoice_id, total, partner_id = await _issue_customer_invoice(client, headers)
    cash_id = await _cash_account_id(client, headers)

    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": total,
            "account_id": cash_id,
            "allocations": [{"sales_invoice_id": invoice_id, "amount": total}],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["number"].startswith("RCT-")  # customer receipts have their own series
    assert body["journal_entry_id"] is not None

    detail = (await client.get(f"/api/v1/payments/payments/{body['id']}", headers=headers)).json()
    assert detail["allocations"][0]["sales_invoice_id"] == invoice_id
    assert Decimal(detail["allocations"][0]["amount"]) == Decimal(total)


async def test_customer_payment_partial_allocation_then_second_payment_completes_it(client):
    _, headers = await _bootstrap_and_login(client)
    invoice_id, total, partner_id = await _issue_customer_invoice(client, headers, total_qty="2", unit_price="100.00")
    cash_id = await _cash_account_id(client, headers)

    half = "100.00"
    first = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": half,
            "account_id": cash_id,
            "allocations": [{"sales_invoice_id": invoice_id, "amount": half}],
        },
    )
    assert first.status_code == 201, first.text

    # Remaining balance can still be allocated in a second payment.
    second = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-06",
            "amount": half,
            "account_id": cash_id,
            "allocations": [{"sales_invoice_id": invoice_id, "amount": half}],
        },
    )
    assert second.status_code == 201, second.text


async def test_overallocating_beyond_invoice_balance_rejected(client):
    _, headers = await _bootstrap_and_login(client)
    invoice_id, total, partner_id = await _issue_customer_invoice(client, headers)
    cash_id = await _cash_account_id(client, headers)

    over_amount = str(float(total) + 50)
    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": over_amount,
            "account_id": cash_id,
            "allocations": [{"sales_invoice_id": invoice_id, "amount": over_amount}],
        },
    )
    assert resp.status_code == 422


async def test_allocating_to_another_customers_invoice_rejected(client):
    _, headers = await _bootstrap_and_login(client)
    invoice_id, total, _real_partner_id = await _issue_customer_invoice(client, headers)
    cash_id = await _cash_account_id(client, headers)

    other_partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Different Customer", "is_customer": True}
    )
    other_partner_id = other_partner_resp.json()["id"]

    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": other_partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": total,
            "account_id": cash_id,
            "allocations": [{"sales_invoice_id": invoice_id, "amount": total}],
        },
    )
    assert resp.status_code == 422


async def test_vendor_payment_against_bill_posts_journal_entry(client):
    _, headers = await _bootstrap_and_login(client)
    bill_id, total, vendor_id = await _issue_vendor_bill(client, headers)
    cash_id = await _cash_account_id(client, headers)

    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "payment_type": "vendor",
            "payment_date": "2026-05-10",
            "amount": total,
            "account_id": cash_id,
            "allocations": [{"vendor_bill_id": bill_id, "amount": total}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["journal_entry_id"] is not None


async def test_payment_isolated_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client, "PayIso A")
    _, headers_b = await _bootstrap_and_login(client, "PayIso B")
    invoice_id, total, partner_id = await _issue_customer_invoice(client, headers_a)
    cash_id = await _cash_account_id(client, headers_a)

    create_resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers_a,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": total,
            "account_id": cash_id,
            "allocations": [{"sales_invoice_id": invoice_id, "amount": total}],
        },
    )
    payment_id = create_resp.json()["id"]

    # Company B must not see company A's payment at all.
    get_resp = await client.get(f"/api/v1/payments/payments/{payment_id}", headers=headers_b)
    assert get_resp.status_code == 404

    list_resp = await client.get("/api/v1/payments/payments", headers=headers_b)
    assert all(p["id"] != payment_id for p in list_resp.json())


async def test_sales_invoice_balance_reflects_unpaid_then_partial_then_paid(client):
    _, headers = await _bootstrap_and_login(client)
    invoice_id, total, partner_id = await _issue_customer_invoice(client, headers, total_qty="2", unit_price="100.00")
    cash_id = await _cash_account_id(client, headers)

    balance = (await client.get(f"/api/v1/payments/balance/sales-invoice/{invoice_id}", headers=headers)).json()
    assert balance["payment_status"] == "unpaid"
    assert Decimal(balance["amount_paid"]) == Decimal("0")
    assert Decimal(balance["balance_due"]) == Decimal(total)

    # `total` (230.00) is 200.00 + 15% VAT, not a round number to split in
    # half — pay a fixed first installment, then whatever remains.
    first_installment = Decimal("100.00")
    remaining_after_first = Decimal(total) - first_installment
    await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": str(first_installment),
            "account_id": cash_id,
            "allocations": [{"sales_invoice_id": invoice_id, "amount": str(first_installment)}],
        },
    )
    balance = (await client.get(f"/api/v1/payments/balance/sales-invoice/{invoice_id}", headers=headers)).json()
    assert balance["payment_status"] == "partially_paid"
    assert Decimal(balance["balance_due"]) == remaining_after_first

    await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-06",
            "amount": str(remaining_after_first),
            "account_id": cash_id,
            "allocations": [{"sales_invoice_id": invoice_id, "amount": str(remaining_after_first)}],
        },
    )
    balance = (await client.get(f"/api/v1/payments/balance/sales-invoice/{invoice_id}", headers=headers)).json()
    assert balance["payment_status"] == "paid"
    assert Decimal(balance["balance_due"]) == Decimal("0")


async def test_vendor_bill_balance_reflects_paid_status(client):
    _, headers = await _bootstrap_and_login(client)
    bill_id, total, vendor_id = await _issue_vendor_bill(client, headers)
    cash_id = await _cash_account_id(client, headers)

    before = (await client.get(f"/api/v1/payments/balance/vendor-bill/{bill_id}", headers=headers)).json()
    assert before["payment_status"] == "unpaid"

    await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "payment_type": "vendor",
            "payment_date": "2026-05-10",
            "amount": total,
            "account_id": cash_id,
            "allocations": [{"vendor_bill_id": bill_id, "amount": total}],
        },
    )
    after = (await client.get(f"/api/v1/payments/balance/vendor-bill/{bill_id}", headers=headers)).json()
    assert after["payment_status"] == "paid"
    assert Decimal(after["balance_due"]) == Decimal("0")


async def test_sales_invoice_list_endpoint_filters_by_partner(client):
    _, headers = await _bootstrap_and_login(client)
    invoice_id, _total, partner_id = await _issue_customer_invoice(client, headers)

    all_invoices = (await client.get("/api/v1/sales/invoices", headers=headers)).json()["items"]
    assert any(inv["id"] == invoice_id for inv in all_invoices)

    filtered = (await client.get(f"/api/v1/sales/invoices?partner_id={partner_id}", headers=headers)).json()["items"]
    assert all(inv["partner_id"] == partner_id for inv in filtered)
    assert any(inv["id"] == invoice_id for inv in filtered)


async def test_vendor_bill_list_endpoint_filters_by_partner(client):
    _, headers = await _bootstrap_and_login(client)
    bill_id, _total, vendor_id = await _issue_vendor_bill(client, headers)

    filtered = (await client.get(f"/api/v1/purchasing/vendor-bills?partner_id={vendor_id}", headers=headers)).json()["items"]
    assert all(bill["partner_id"] == vendor_id for bill in filtered)
    assert any(bill["id"] == bill_id for bill in filtered)


async def test_concurrent_payments_cannot_jointly_overallocate_same_invoice(client):
    """Two simultaneous payments each try to allocate the FULL invoice
    total. The row lock (`get_by_id_for_update`) must serialize them: one
    succeeds, the other correctly fails the outstanding-balance check
    against the now-updated allocation total — never both succeeding."""
    _, headers = await _bootstrap_and_login(client)
    invoice_id, total, partner_id = await _issue_customer_invoice(client, headers)
    cash_id = await _cash_account_id(client, headers)

    def _payload():
        return {
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": total,
            "account_id": cash_id,
            "allocations": [{"sales_invoice_id": invoice_id, "amount": total}],
        }

    results = await asyncio.gather(
        client.post("/api/v1/payments/payments", headers=headers, json=_payload()),
        client.post("/api/v1/payments/payments", headers=headers, json=_payload()),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 422], f"expected exactly one success and one rejection, got {statuses}"

    balance = (await client.get(f"/api/v1/payments/balance/sales-invoice/{invoice_id}", headers=headers)).json()
    assert Decimal(balance["amount_paid"]) == Decimal(total)
    assert Decimal(balance["balance_due"]) == Decimal("0")
