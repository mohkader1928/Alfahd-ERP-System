"""P0-1 (Phase-One audit closure) — VAT must come from the real, configured
`TaxRate` mechanism, not an assumed 15% constant.

Before this fix, `SalesInvoiceService.issue_invoice_from_order`/
`issue_credit_note_for_lines` and `VendorBillService.register_bill`/
`update_bill`/`issue_debit_note_for_lines` all hardcoded
`Decimal("15.00")` regardless of the `tax_rate_id` stored on the line.
Every company already has 4 real seeded `TaxRate` rows
(`ChartOfAccountsService.seed_default_tax_rates`, run automatically on
company registration) — these tests prove the computation now actually
reads that configuration instead of the old constant, that a genuinely
different rate (zero-rated) is honored exactly, that company isolation
holds, and that every pre-existing caller using the historical placeholder
`tax_rate_id` still computes the correct standard rate unchanged.
"""

from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap(client, label: str) -> dict:
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
    return {"company_id": company_id, "branch_id": branch_id, "headers": headers}


async def _tax_rates(client, headers) -> list[dict]:
    resp = await client.get("/api/v1/accounting/tax-rates", headers=headers)
    assert resp.status_code == 200
    return resp.json()


async def _rate_id(client, headers, kind: str) -> str:
    rates = await _tax_rates(client, headers)
    match = next(r for r in rates if r["kind"] == kind)
    return match["id"]


async def _create_customer_and_product(client, headers, sales_price: str = "100.00") -> tuple[str, str]:
    partner = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "VAT Test Customer", "is_customer": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "VAT Test Product", "sales_price": sales_price},
    )
    assert partner.status_code == 201 and product.status_code == 201
    return partner.json()["id"], product.json()["id"]


async def _issue_invoice(client, headers, *, partner_id: str, product_id: str, tax_rate_id: str, unit_price: str = "100.00"):
    quote = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "2", "unit_price": unit_price, "tax_rate_id": tax_rate_id}],
        },
    )
    assert quote.status_code == 201
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    return invoice_resp.json()["invoice"]


async def _create_vendor_and_product(client, headers) -> tuple[str, str]:
    vendor = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "VAT Test Vendor", "is_vendor": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "VAT Test Purchase Product", "sales_price": "10.00"},
    )
    assert vendor.status_code == 201 and product.status_code == 201
    return vendor.json()["id"], product.json()["id"]


async def _receive_and_bill(client, headers, *, vendor_id: str, product_id: str, tax_rate_id: str, unit_price: str = "20.00"):
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True})
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": "2026-05-01",
            "lines": [{"product_id": product_id, "qty": "10", "unit_price": unit_price, "tax_rate_id": tax_rate_id}],
        },
    )
    assert po_resp.status_code == 201
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)

    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]

    # record_receipt auto-bills at the PO's own price (register_bill is the
    # exact call site under test — this exercises it, not a manual
    # standalone POST /vendor-bills).
    receipt_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "10"}]},
    )
    assert receipt_resp.status_code == 201

    order_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    assert order_detail["order"]["status"] == "done"

    bills = (await client.get("/api/v1/purchasing/vendor-bills", headers=headers)).json()
    bill = next(b for b in bills["items"] if b["purchase_order_id"] == order_id)
    return bill


async def test_tax_rate_list_endpoint_returns_seeded_rates(client):
    env = await _bootstrap(client, f"TaxList-{unique_vat()[:6]}")
    rates = await _tax_rates(client, env["headers"])
    kinds = {r["kind"] for r in rates}
    assert kinds == {"standard", "zero_rated", "exempt", "out_of_scope"}
    standard = next(r for r in rates if r["kind"] == "standard")
    assert Decimal(standard["rate_percent"]) == Decimal("15.00")
    assert all(r["company_id"] == env["company_id"] for r in rates)


async def test_sales_invoice_uses_company_configured_standard_rate(client):
    """Requirement #2: a configured 15% rate produces the expected result —
    using the real (not placeholder) standard-rate id end to end."""
    env = await _bootstrap(client, f"SalesStd-{unique_vat()[:6]}")
    headers = env["headers"]
    standard_id = await _rate_id(client, headers, "standard")
    partner_id, product_id = await _create_customer_and_product(client, headers)

    invoice = await _issue_invoice(client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=standard_id)

    assert Decimal(invoice["subtotal_amount"]) == Decimal("200.00")
    assert Decimal(invoice["tax_amount"]) == Decimal("30.00")
    assert Decimal(invoice["total_amount"]) == Decimal("230.00")


async def test_sales_invoice_uses_different_configured_rate_not_hardcoded(client):
    """Requirement #3: a DIFFERENT configured rate proves the system is
    actually reading configuration, not still secretly hardcoded to 15% —
    the old code would have produced tax_amount=30.00 here regardless of
    which tax_rate_id was sent; this must be exactly 0.00."""
    env = await _bootstrap(client, f"SalesZero-{unique_vat()[:6]}")
    headers = env["headers"]
    zero_rated_id = await _rate_id(client, headers, "zero_rated")
    partner_id, product_id = await _create_customer_and_product(client, headers)

    invoice = await _issue_invoice(client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=zero_rated_id)

    assert Decimal(invoice["subtotal_amount"]) == Decimal("200.00")
    assert Decimal(invoice["tax_amount"]) == Decimal("0.00")
    assert Decimal(invoice["total_amount"]) == Decimal("200.00")


async def test_purchasing_vendor_bill_uses_different_configured_rate(client):
    """Requirement #6: Sales and Purchasing remain consistent — the same
    zero-rated proof, on the Purchasing side (register_bill, exercised via
    the goods-receipt auto-billing path)."""
    env = await _bootstrap(client, f"PurchZero-{unique_vat()[:6]}")
    headers = env["headers"]
    zero_rated_id = await _rate_id(client, headers, "zero_rated")
    vendor_id, product_id = await _create_vendor_and_product(client, headers)

    bill = await _receive_and_bill(client, headers, vendor_id=vendor_id, product_id=product_id, tax_rate_id=zero_rated_id)

    assert Decimal(bill["subtotal_amount"]) == Decimal("200.00")
    assert Decimal(bill["tax_amount"]) == Decimal("0.00")
    assert Decimal(bill["total_amount"]) == Decimal("200.00")


async def test_tax_rate_company_isolation(client):
    """Requirement #4: company isolation. Company A's zero-rated tax_rate_id
    must NOT be usable to zero out Company B's tax — RLS blocks the direct
    lookup, and the fallback-to-own-standard-rate path must kick in, giving
    Company B's real 15%, not a leaked 0% from Company A."""
    company_a = await _bootstrap(client, f"IsoA-{unique_vat()[:6]}")
    company_b = await _bootstrap(client, f"IsoB-{unique_vat()[:6]}")

    a_zero_rated_id = await _rate_id(client, company_a["headers"], "zero_rated")

    partner_id, product_id = await _create_customer_and_product(client, company_b["headers"])
    invoice = await _issue_invoice(
        client, company_b["headers"], partner_id=partner_id, product_id=product_id, tax_rate_id=a_zero_rated_id
    )

    # Falls back to Company B's own standard rate (15%), proving Company A's
    # rate was never actually read for Company B's invoice.
    assert Decimal(invoice["subtotal_amount"]) == Decimal("200.00")
    assert Decimal(invoice["tax_amount"]) == Decimal("30.00")
    assert Decimal(invoice["total_amount"]) == Decimal("230.00")


async def test_historical_placeholder_tax_rate_id_still_computes_standard_rate(client):
    """Requirement #5: historical/posting behavior is not unintentionally
    changed. Every pre-existing test and any pre-fix frontend build sends
    the exact literal placeholder UUID below as tax_rate_id — it does not
    resolve to a real row for any company, so it must fall back to this
    company's own configured standard rate (still 15%), exactly the value
    the old hardcoded code always produced. This is what keeps the entire
    existing test suite passing unmodified."""
    env = await _bootstrap(client, f"Legacy-{unique_vat()[:6]}")
    headers = env["headers"]
    partner_id, product_id = await _create_customer_and_product(client, headers)

    invoice = await _issue_invoice(
        client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=TAX_RATE_PLACEHOLDER
    )

    assert Decimal(invoice["subtotal_amount"]) == Decimal("200.00")
    assert Decimal(invoice["tax_amount"]) == Decimal("30.00")
    assert Decimal(invoice["total_amount"]) == Decimal("230.00")


async def test_journal_entry_balances_with_zero_rated_tax(client):
    """Requirement #7: accounting entries remain balanced even when tax is
    genuinely zero (no VAT line at all, not a zero-value line) — total
    debits must still equal total credits on the posted JE."""
    env = await _bootstrap(client, f"JEBalance-{unique_vat()[:6]}")
    headers = env["headers"]
    zero_rated_id = await _rate_id(client, headers, "zero_rated")
    partner_id, product_id = await _create_customer_and_product(client, headers)

    invoice = await _issue_invoice(client, headers, partner_id=partner_id, product_id=product_id, tax_rate_id=zero_rated_id)
    assert invoice["journal_entry_id"] is not None

    je_resp = await client.get(f"/api/v1/accounting/journal-entries/{invoice['journal_entry_id']}", headers=headers)
    assert je_resp.status_code == 200
    je = je_resp.json()
    total_debit = sum(Decimal(line["debit"]) for line in je["lines"])
    total_credit = sum(Decimal(line["credit"]) for line in je["lines"])
    assert total_debit == total_credit
    assert total_debit == Decimal("200.00")
    # No VAT-payable line at all when tax is zero, not a zero-valued one.
    assert len(je["lines"]) == 2
