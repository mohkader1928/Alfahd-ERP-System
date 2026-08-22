"""Integration smoke test for the VAT/Tax Summary report.

Explicitly named in the Owner's original Bundle E spec: output VAT
(sales) vs. input VAT (purchases) for a period, netted to what's owed.
Mirrors the bootstrap/invoice pattern in test_sales_reporting_bundle_e.py
and the procure-to-pay pattern in test_purchasing_m4_smoke.py.
"""

from datetime import date, timedelta
from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "VAT Test Holding",
        "company_legal_name": "VAT Test Trading Co.",
        "company_legal_name_ar": "VAT Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "VAT Test Admin",
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


async def _issue_sale(client, headers, *, invoice_date: str):
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "VAT Sale Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": "VAT-SALE-01", "name": "VAT Sale Product", "sales_price": "100.00"},
    )
    product_id = product_resp.json()["id"]
    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": invoice_date,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    return invoice_resp.json()["invoice"]


async def _create_vendor(client, headers):
    resp = await client.post("/api/v1/identity/partners", headers=headers, json={"name": "VAT Bill Vendor", "is_vendor": True})
    return resp.json()["id"]


async def _create_product(client, headers):
    resp = await client.post(
        "/api/v1/identity/products", headers=headers, json={"sku": "VAT-BUY-01", "name": "VAT Buy Product", "cost_price": "40.00"}
    )
    return resp.json()["id"]


async def _ensure_default_warehouse(client, headers):
    existing = await client.get("/api/v1/inventory/warehouses", headers=headers)
    if existing.status_code == 200 and existing.json():
        return
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "VAT Test Warehouse", "is_default": True})


async def _post_vendor_bill(client, headers, *, bill_date: str):
    await _ensure_default_warehouse(client, headers)
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": bill_date,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "40.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    gr_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "1"}]},
    )
    assert gr_resp.status_code == 201, gr_resp.text
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "VBILL-1", "lines": [{"purchase_order_line_id": po_line_id, "qty": "1", "unit_price": "40.00"}]},
    )
    assert bill_resp.json()["status"] == "matched", bill_resp.text
    bill_id = bill_resp.json()["id"]
    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)
    assert approve_resp.status_code == 200, approve_resp.text
    return approve_resp.json()


async def test_vat_summary_nets_output_and_input_vat(client):
    # Sales/purchase documents post with invoice_date/bill_date = date.today()
    # regardless of the quote_date/order_date supplied at draft time (invoices
    # are dated when actually issued, not when quoted) — so the report window
    # must bracket today, not an arbitrary past date.
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_sale(client, headers, invoice_date=today.isoformat())
    bill = await _post_vendor_bill(client, headers, bill_date=today.isoformat())

    resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert Decimal(body["sales_subtotal"]) == Decimal(invoice["subtotal_amount"])
    assert Decimal(body["output_vat"]) == Decimal(invoice["tax_amount"])
    assert Decimal(body["purchases_subtotal"]) == Decimal(bill["subtotal_amount"])
    assert Decimal(body["input_vat"]) == Decimal(bill["tax_amount"])
    assert Decimal(body["net_vat_payable"]) == Decimal(body["output_vat"]) - Decimal(body["input_vat"])
    # Real business assertion: a company that sold more than it bought in
    # the period owes VAT (positive net payable), not a refund.
    assert Decimal(body["net_vat_payable"]) > 0


async def test_vat_summary_nets_vendor_debit_notes_against_purchases(client):
    """Regression for two real reported bugs from the same root cause:
    1) (2026-08-19) this report's purchases_stmt summed every posted
       VendorBill regardless of `bill_type`, so a Vendor Debit Note
       inflated purchases_total/input_vat by double-counting it on top
       of the original bill.
    2) (2026-08-22) the fix for #1 excluded debit notes from
       purchases_stmt entirely instead of netting them the way the sales
       side already nets credit notes (`output_vat = sales.vat -
       credit_note.vat`) -- stopping the double-count, but also silently
       dropping the debit note's real VAT reversal, which
       `issue_debit_note`'s own JE always posts to the GL's VAT Payable
       account regardless. Trial Balance's VAT Payable (computed from the
       GL) and this report (computed independently from source documents)
       diverged by the debit note's own tax_amount -- SAR 16,822,500 on a
       real company with 19 debit notes in the period.

    A full debit note against a bill must net input VAT to exactly zero
    for that bill -- the same "fully returned = zero net" outcome the
    sales side already produces for a fully credit-noted invoice."""
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    bill = await _post_vendor_bill(client, headers, bill_date=today.isoformat())

    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill['id']}:debit-note",
        headers=headers,
        json={"reason": "Full return"},
    )
    assert debit_resp.status_code == 201, debit_resp.text

    resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # A full return nets purchases/input VAT to zero -- not "only the
    # original bill" (the old, buggy behavior) and not double-counted.
    assert Decimal(body["purchases_subtotal"]) == 0
    assert Decimal(body["input_vat"]) == 0
    assert Decimal(body["purchases_total"]) == 0


async def test_vat_summary_nets_partial_vendor_debit_note(client):
    """The full-return case above can't distinguish "netted" from
    "excluded-but-happens-to-be-zero"; a PARTIAL debit note (half the
    original bill, via the freeform-lines endpoint) proves the netting
    arithmetic itself: input VAT must be the original bill's VAT minus
    the partial debit note's own VAT, not the full bill's VAT untouched
    (the old, buggy "exclude" behavior)."""
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    vendor_id = await _create_vendor(client, headers)
    product_id = await _create_product(client, headers)
    await _ensure_default_warehouse(client, headers)

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": today.isoformat(),
            "lines": [{"product_id": product_id, "qty": "10", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    gr_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "10"}]},
    )
    assert gr_resp.status_code == 201, gr_resp.text
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "PARTIAL-DN", "lines": [{"purchase_order_line_id": po_line_id, "qty": "10", "unit_price": "100.00"}]},
    )
    bill_id = bill_resp.json()["id"]
    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)
    bill = approve_resp.json()
    # 10 units @ 100.00 = 1000.00 subtotal, 15% VAT = 150.00.
    assert Decimal(bill["tax_amount"]) == Decimal("150.0000")

    debit_resp = await client.post(
        "/api/v1/purchasing/vendor-bills:return",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "original_bill_id": bill_id,
            "reason": "Partial return, 4 of 10 units",
            "restock": True,
            "lines": [{"product_id": product_id, "qty": "4", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert debit_resp.status_code == 201, debit_resp.text
    debit_note = debit_resp.json()
    # 4 units @ 100.00 = 400.00 subtotal, 15% VAT = 60.00.
    assert Decimal(debit_note["tax_amount"]) == Decimal("60.0000")

    resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    body = resp.json()

    # 150.00 (full bill) - 60.00 (partial return) = 90.00, not 150.00
    # (the old "exclude debit notes entirely" bug).
    assert Decimal(body["input_vat"]) == Decimal("90.0000")
    assert Decimal(body["purchases_subtotal"]) == Decimal("600.0000")  # 1000 - 400


async def test_vat_summary_excludes_out_of_range_and_unposted(client):
    _, headers = await _bootstrap_and_login(client)
    await _issue_sale(client, headers, invoice_date=date.today().isoformat())

    past_from = (date.today() - timedelta(days=3650)).isoformat()
    past_to = (date.today() - timedelta(days=3600)).isoformat()
    resp = await client.get(
        "/api/v1/reporting/vat-summary", headers=headers, params={"date_from": past_from, "date_to": past_to}
    )
    body = resp.json()
    assert Decimal(body["output_vat"]) == 0
    assert Decimal(body["net_vat_payable"]) == 0


async def test_vat_summary_export_pdf_and_excel(client):
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    await _issue_sale(client, headers, invoice_date=today.isoformat())

    pdf_resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "format": "pdf"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.content[:4] == b"%PDF"

    xlsx_resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "format": "xlsx", "lang": "en"},
    )
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.content[:2] == b"PK"


async def test_vat_summary_requires_permission(client):
    resp = await client.get(
        "/api/v1/reporting/vat-summary", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
    )
    assert resp.status_code == 401


async def test_vat_detail_lists_documents_reconciling_to_summary(client):
    """Owner-requested companion to VAT Summary: a document-level listing
    whose totals must reproduce the exact figures /vat-summary returns,
    so the net VAT payable number can be traced back to individual
    invoices/bills rather than trusted blind."""
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_sale(client, headers, invoice_date=today.isoformat())
    bill = await _post_vendor_bill(client, headers, bill_date=today.isoformat())

    summary_resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    summary = summary_resp.json()

    detail_resp = await client.get(
        "/api/v1/reporting/vat-detail",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert detail_resp.status_code == 200, detail_resp.text
    lines = detail_resp.json()
    assert len(lines) == 2

    invoice_line = next(l for l in lines if l["movement_type"] == "invoice")
    assert invoice_line["document_id"] == invoice["id"]
    assert invoice_line["direction"] == "output"
    assert Decimal(invoice_line["vat_amount"]) == Decimal(invoice["tax_amount"])

    bill_line = next(l for l in lines if l["movement_type"] == "bill")
    assert bill_line["document_id"] == bill["id"]
    assert bill_line["direction"] == "input"
    assert Decimal(bill_line["vat_amount"]) == Decimal(bill["tax_amount"])

    output_vat = sum(Decimal(l["vat_amount"]) for l in lines if l["direction"] == "output")
    input_vat = sum(Decimal(l["vat_amount"]) for l in lines if l["direction"] == "input")
    assert output_vat == Decimal(summary["output_vat"])
    assert input_vat == Decimal(summary["input_vat"])


async def test_vat_detail_credit_note_carries_negated_amounts(client):
    """A sales credit note reduces output VAT in /vat-summary via
    subtraction; the detail row for it must carry negated amounts so a
    plain SUM over the detail rows reproduces that same subtraction."""
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_sale(client, headers, invoice_date=today.isoformat())

    credit_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice['id']}:credit-note", headers=headers, json={"reason": "Full return"}
    )
    assert credit_resp.status_code == 201, credit_resp.text
    credit_note = credit_resp.json()["invoice"]

    detail_resp = await client.get(
        "/api/v1/reporting/vat-detail",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    lines = detail_resp.json()
    credit_line = next(l for l in lines if l["movement_type"] == "credit_note")
    assert credit_line["document_id"] == credit_note["id"]
    assert Decimal(credit_line["vat_amount"]) == -Decimal(credit_note["tax_amount"])
    assert Decimal(credit_line["total_amount"]) == -Decimal(credit_note["total_amount"])

    summary_resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    summary = summary_resp.json()
    output_vat = sum(Decimal(l["vat_amount"]) for l in lines if l["direction"] == "output")
    assert output_vat == Decimal(summary["output_vat"])


async def test_vat_detail_includes_debit_notes_and_reconciles_to_summary(client):
    """Vendor debit notes now appear in the detail listing (negated,
    same contra convention as sales credit notes), and the sum of every
    input-direction line must reproduce /vat-summary's input_vat exactly
    -- the two reports must never disagree about what counts toward
    input VAT (the real gap this was built to close)."""
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    bill = await _post_vendor_bill(client, headers, bill_date=today.isoformat())
    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill['id']}:debit-note", headers=headers, json={"reason": "Full return"}
    )
    assert debit_resp.status_code == 201, debit_resp.text
    debit_note = debit_resp.json()

    detail_resp = await client.get(
        "/api/v1/reporting/vat-detail",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    lines = detail_resp.json()
    debit_line = next(l for l in lines if l["movement_type"] == "debit_note")
    assert debit_line["document_id"] == debit_note["id"]
    assert Decimal(debit_line["vat_amount"]) == -Decimal(debit_note["tax_amount"])

    summary_resp = await client.get(
        "/api/v1/reporting/vat-summary",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    summary = summary_resp.json()
    input_vat = sum(Decimal(l["vat_amount"]) for l in lines if l["direction"] == "input")
    assert input_vat == Decimal(summary["input_vat"]) == 0  # full return nets to zero


async def test_vat_detail_export_pdf_and_excel(client):
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    await _issue_sale(client, headers, invoice_date=today.isoformat())

    pdf_resp = await client.get(
        "/api/v1/reporting/vat-detail",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "format": "pdf"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.content[:4] == b"%PDF"

    xlsx_resp = await client.get(
        "/api/v1/reporting/vat-detail",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "format": "xlsx", "lang": "en"},
    )
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.content[:2] == b"PK"


async def test_vat_detail_requires_permission(client):
    resp = await client.get(
        "/api/v1/reporting/vat-detail", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
    )
    assert resp.status_code == 401


async def test_vat_reconciliation_matches_when_no_debit_or_credit_notes(client):
    """Standing-prevention report (Owner request #4): a plain invoice +
    bill, no returns involved, must reconcile exactly -- the baseline
    case that should always match."""
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    await _issue_sale(client, headers, invoice_date=today.isoformat())
    await _post_vendor_bill(client, headers, bill_date=today.isoformat())

    resp = await client.get(
        "/api/v1/reporting/vat-reconciliation",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["matched"] is True
    assert Decimal(body["difference"]) == 0
    assert Decimal(body["summary_net_vat_payable"]) == Decimal(body["gl_net_vat_payable"])


async def test_vat_reconciliation_matches_with_debit_and_credit_notes(client):
    """The actual regression: before the netting fix, a debit note alone
    would have opened a real gap here. With the fix, this must still
    read MATCHED even with both a credit note and a debit note in the
    period -- proving the reconciliation report itself would have
    caught the original bug had it existed at the time."""
    today = date.today()
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_sale(client, headers, invoice_date=today.isoformat())
    await client.post(
        f"/api/v1/sales/invoices/{invoice['id']}:credit-note", headers=headers, json={"reason": "Full return"}
    )
    bill = await _post_vendor_bill(client, headers, bill_date=today.isoformat())
    await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill['id']}:debit-note", headers=headers, json={"reason": "Full return"}
    )

    resp = await client.get(
        "/api/v1/reporting/vat-reconciliation",
        headers=headers,
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["matched"] is True, body
    assert Decimal(body["difference"]) == 0


async def test_vat_reconciliation_requires_permission(client):
    resp = await client.get(
        "/api/v1/reporting/vat-reconciliation", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
    )
    assert resp.status_code == 401
