"""Commercial Performance Stage 2D — Collection Representative attribution
on customer receipts (Payment.collection_rep_id).

Covers exactly the approved Stage 2D scope: an independent attribution
field on Payment, distinct from SalesInvoice.sales_rep_id, never derived
from the invoice(s) a payment settles, customer-side only. No commission
calculation — that is explicitly out of scope for this stage.
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


async def _cash_account_id(client, headers) -> str:
    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    return next(a["id"] for a in accounts if a["code"] == "1100")


async def _create_sales_rep(client, headers, *, name: str = "Ahmed", code: str = "REP001") -> dict:
    resp = await client.post("/api/v1/identity/sales-representatives", headers=headers, json={"name": name, "code": code})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _issue_customer_invoice(client, headers, *, partner_id: str, sales_rep_id: str | None = None) -> tuple[str, str]:
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Stage2D Widget", "sales_price": "100.00"},
    )
    product_id = product_resp.json()["id"]

    quote_payload = {
        "partner_id": partner_id,
        "quote_date": "2026-06-01",
        "lines": [{"product_id": product_id, "qty": "1", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
    }
    if sales_rep_id is not None:
        quote_payload["sales_rep_id"] = sales_rep_id
    quote_resp = await client.post("/api/v1/sales/quotations", headers=headers, json=quote_payload)
    assert quote_resp.status_code == 201, quote_resp.text
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text
    invoice = invoice_resp.json()["invoice"]
    return invoice["id"], invoice["total_amount"]


async def test_customer_receipt_saves_collection_rep_id(client):
    """TEST: customer receipt saves collection_rep_id."""
    _, headers = await _bootstrap_and_login(client, f"S2D-Save-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers)
    cash_id = await _cash_account_id(client, headers)
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Stage2D Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    invoice_id, total = await _issue_customer_invoice(client, headers, partner_id=partner_id)

    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": total,
            "account_id": cash_id,
            "collection_rep_id": rep["id"],
            "allocations": [{"sales_invoice_id": invoice_id, "amount": total}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["collection_rep_id"] == rep["id"]

    reloaded = (await client.get(f"/api/v1/payments/payments/{resp.json()['id']}", headers=headers)).json()
    assert reloaded["payment"]["collection_rep_id"] == rep["id"]


async def test_sales_rep_and_collection_rep_may_legitimately_differ(client):
    """TEST: the person who sells is not necessarily the person who
    collects — both attributions must be independently correct on the
    same commercial transaction."""
    _, headers = await _bootstrap_and_login(client, f"S2D-Differ-{unique_vat()[:6]}")
    seller = await _create_sales_rep(client, headers, name="Ahmed", code="REP-SELLER")
    collector = await _create_sales_rep(client, headers, name="Mohammed", code="REP-COLLECTOR")
    cash_id = await _cash_account_id(client, headers)
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Stage2D Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    invoice_id, total = await _issue_customer_invoice(client, headers, partner_id=partner_id, sales_rep_id=seller["id"])

    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": total,
            "account_id": cash_id,
            "collection_rep_id": collector["id"],
            "allocations": [{"sales_invoice_id": invoice_id, "amount": total}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["collection_rep_id"] == collector["id"]
    assert resp.json()["collection_rep_id"] != seller["id"]

    invoice_reloaded = (await client.get(f"/api/v1/sales/invoices/{invoice_id}", headers=headers)).json()
    assert invoice_reloaded["invoice"]["sales_rep_id"] == seller["id"]


async def test_changing_customer_default_rep_later_does_not_alter_old_receipt(client):
    """TEST: historical accuracy for receipts, mirroring the same guarantee
    already proven for quotations/orders/invoices/credit notes."""
    _, headers = await _bootstrap_and_login(client, f"S2D-Hist-{unique_vat()[:6]}")
    rep_ahmed = await _create_sales_rep(client, headers, name="Ahmed", code="REP-JAN")
    rep_mohamed = await _create_sales_rep(client, headers, name="Mohamed", code="REP-MAR")
    cash_id = await _cash_account_id(client, headers)
    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "Stage2D Customer", "is_customer": True, "default_sales_rep_id": rep_ahmed["id"]},
    )
    partner_id = partner_resp.json()["id"]
    invoice_id, total = await _issue_customer_invoice(client, headers, partner_id=partner_id)

    payment_resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": total,
            "account_id": cash_id,
            "collection_rep_id": rep_ahmed["id"],
            "allocations": [{"sales_invoice_id": invoice_id, "amount": total}],
        },
    )
    payment_id = payment_resp.json()["id"]

    await client.patch(
        f"/api/v1/identity/partners/{partner_id}",
        headers=headers,
        json={"name": "Stage2D Customer", "is_customer": True, "default_sales_rep_id": rep_mohamed["id"]},
    )

    reloaded = (await client.get(f"/api/v1/payments/payments/{payment_id}", headers=headers)).json()
    assert reloaded["payment"]["collection_rep_id"] == rep_ahmed["id"]


async def test_cross_company_collection_rep_assignment_is_rejected(client):
    """TEST: cross-company collection representative assignment is
    rejected."""
    _, headers_a = await _bootstrap_and_login(client, f"S2D-CrossA-{unique_vat()[:6]}")
    _, headers_b = await _bootstrap_and_login(client, f"S2D-CrossB-{unique_vat()[:6]}")
    rep_in_b = await _create_sales_rep(client, headers_b, code="REP-B-ONLY")
    cash_id = await _cash_account_id(client, headers_a)
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers_a, json={"name": "Stage2D Customer A", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    invoice_id, total = await _issue_customer_invoice(client, headers_a, partner_id=partner_id)

    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers_a,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": total,
            "account_id": cash_id,
            "collection_rep_id": rep_in_b["id"],
            "allocations": [{"sales_invoice_id": invoice_id, "amount": total}],
        },
    )
    assert resp.status_code == 422, resp.text


async def test_payment_without_collection_rep_field_remains_backward_compatible(client):
    """API backward compatibility: omitting collection_rep_id entirely
    still works, stays NULL."""
    _, headers = await _bootstrap_and_login(client, f"S2D-Compat-{unique_vat()[:6]}")
    cash_id = await _cash_account_id(client, headers)
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Stage2D Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    invoice_id, total = await _issue_customer_invoice(client, headers, partner_id=partner_id)

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
    assert resp.json()["collection_rep_id"] is None


async def test_vendor_payment_unaffected_and_ignores_collection_rep(client):
    """Regression: vendor payments (payment_type = 'vendor') are
    completely unaffected — no collection-rep behavior applies there."""
    _, headers = await _bootstrap_and_login(client, f"S2D-Vendor-{unique_vat()[:6]}")
    cash_id = await _cash_account_id(client, headers)
    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Stage2D Vendor", "is_vendor": True}
    )
    vendor_id = vendor_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Stage2D Steel", "sales_price": "50.00"},
    )
    product_id = product_resp.json()["id"]
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "5", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "5"}]},
    )
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "5", "unit_price": "20.00"}]},
    )
    bill = bill_resp.json()

    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "payment_type": "vendor",
            "payment_date": "2026-06-05",
            "amount": bill["total_amount"],
            "account_id": cash_id,
            "allocations": [{"vendor_bill_id": bill["id"], "amount": bill["total_amount"]}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["collection_rep_id"] is None
    assert resp.json()["journal_entry_id"] is not None
