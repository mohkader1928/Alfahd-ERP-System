"""Integration smoke test for Milestone 1b — Customer/Vendor Subledgers and
AR/AP Aging.

Every figure here is produced by real documents posted through the real
API (invoices, credit notes, vendor bills, payments) — nothing is
hand-inserted. The one test that matters most (`test_subledgers_reconcile
_...`) proves the Subledger cannot silently drift from the General
Ledger's own AR/AP account balance, which is the actual correctness
requirement this Milestone exists to satisfy, not just "the endpoint
returns 200."

Invoice/bill dates are always `date.today()` in this codebase (confirmed
by reading `sales/application/services.py` and
`purchasing/application/services.py` — neither ever accepts a custom
date) — tests use `date_from`/`date_to` windows relative to today rather
than fixed historical dates, which the earlier Accounting-report tests
could use because Journal Entries (unlike Sales/Purchasing documents) do
accept an explicit `entry_date`.
"""

from datetime import date, timedelta
from decimal import Decimal

from src.modules.payments.application.services import _aging_row
from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client, label: str = "Subledger Test"):
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
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": company_id,
        "X-Branch-Id": branch_id,
    }
    return company_id, headers


async def _cash_account_id(client, headers) -> str:
    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    return next(a["id"] for a in accounts if a["code"] == "1100")


async def _ensure_default_warehouse(client, headers) -> None:
    """A fresh company's bootstrap seeds a Chart of Accounts automatically
    (via the CompanyRegistered event) but does NOT seed a default
    warehouse -- confirmed by reading `WarehouseRepository
    .get_default_for_company` and reproducing the failure directly against
    a fresh bootstrap. Without one, `POST .../goods-receipts` always fails
    with 422 "No default warehouse configured", which in turn makes every
    vendor bill "mismatched" (billed qty > received qty 0) regardless of
    what was actually ordered. This is a real, pre-existing gap in company
    onboarding, out of this Milestone's scope to fix -- reported as a
    Known Limitation, not silently patched. Tests create the warehouse
    explicitly, the same one real step a user would take from the
    Inventory screen before receiving goods for the first time."""
    existing = (await client.get("/api/v1/inventory/warehouses", headers=headers)).json()
    if any(w["is_default"] for w in existing):
        return
    await client.post(
        "/api/v1/inventory/warehouses",
        headers=headers,
        json={"name": "Main Warehouse", "is_default": True},
    )


async def _issue_customer_invoice(
    client, headers, name: str, *, qty="2", unit_price="100.00", partner_id: str | None = None
) -> tuple[str, str, str]:
    """Simplified (no vat_number) B2C invoice, matching the exact pattern
    already established in test_payments_m6_smoke.py — reused verbatim so
    this test isn't inventing a second way to create the same fixture.
    Pass an existing `partner_id` to issue a second invoice to the same
    customer instead of creating a new one."""
    if partner_id is None:
        partner_resp = await client.post(
            "/api/v1/identity/partners", headers=headers, json={"name": name, "is_customer": True}
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
            "quote_date": str(date.today()),
            "lines": [
                {
                    "product_id": product_id,
                    "qty": qty,
                    "unit_price": unit_price,
                    "tax_rate_id": TAX_RATE_PLACEHOLDER,
                }
            ],
        },
    )
    order_resp = await client.post(
        f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers
    )
    invoice_resp = await client.post(
        f"/api/v1/sales/orders/{order_resp.json()['id']}:invoice", headers=headers
    )
    assert invoice_resp.status_code == 201, invoice_resp.text
    invoice = invoice_resp.json()["invoice"]
    return invoice["id"], invoice["total_amount"], partner_id


async def _issue_vendor_bill(
    client, headers, name: str, *, qty="5", unit_price="20.00"
) -> tuple[str, str, str]:
    await _ensure_default_warehouse(client, headers)
    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": name, "is_vendor": True}
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
            "order_date": str(date.today()),
            "lines": [
                {
                    "product_id": product_id,
                    "qty": qty,
                    "unit_price": unit_price,
                    "tax_rate_id": TAX_RATE_PLACEHOLDER,
                }
            ],
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
        json={
            "lines": [{"purchase_order_line_id": po_line_id, "qty": qty, "unit_price": unit_price}]
        },
    )
    assert bill_resp.status_code == 201, bill_resp.text
    bill = bill_resp.json()

    # A vendor bill only posts its own Journal Entry once approved (a
    # matched-but-unapproved bill has no accounting impact yet) — approve
    # it here so this fixture represents a real, complete bill, the same
    # as a real user would do before recording a payment against it.
    approve_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill['id']}:approve", headers=headers
    )
    assert approve_resp.status_code == 200, approve_resp.text
    bill = approve_resp.json()

    return bill["id"], bill["total_amount"], vendor_id


async def _pay(
    client,
    headers,
    *,
    partner_id,
    payment_type,
    payment_date,
    amount,
    account_id,
    target_key,
    target_id,
):
    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": payment_type,
            "payment_date": payment_date,
            "amount": amount,
            "account_id": account_id,
            "allocations": [{target_key: target_id, "amount": amount}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_customer_subledger_opening_balance_and_running_balance(client):
    _, headers = await _bootstrap_and_login(client)
    cash = await _cash_account_id(client, headers)
    today = date.today()

    invoice_a_id, invoice_a_total, partner_id = await _issue_customer_invoice(
        client, headers, "Ledger Customer A"
    )
    _, invoice_b_total, _ = await _issue_customer_invoice(
        client, headers, "Ledger Customer A", qty="1", unit_price="100.00", partner_id=partner_id
    )

    date_from = today + timedelta(days=1)
    date_to = today + timedelta(days=365)

    # A partial payment against invoice A, dated inside the query window.
    await _pay(
        client,
        headers,
        partner_id=partner_id,
        payment_type="customer",
        payment_date=str(today + timedelta(days=10)),
        amount="100.00",
        account_id=cash,
        target_key="sales_invoice_id",
        target_id=invoice_a_id,
    )

    resp = await client.get(
        f"/api/v1/payments/subledger/customer/{partner_id}",
        headers=headers,
        params={"date_from": str(date_from), "date_to": str(date_to)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Opening balance = everything dated before date_from, i.e. both
    # invoices (today's date) net of nothing else yet.
    expected_opening = Decimal(invoice_a_total) + Decimal(invoice_b_total)
    assert Decimal(body["opening_balance"]) == expected_opening
    assert len(body["lines"]) == 1  # only the payment falls inside the window
    assert body["lines"][0]["movement_type"] == "payment"
    assert Decimal(body["lines"][0]["credit"]) == Decimal("100.00")
    expected_closing = expected_opening - Decimal("100.00")
    assert Decimal(body["closing_balance"]) == expected_closing
    assert body["partner_name"] == "Ledger Customer A"


async def test_customer_subledger_credit_note_nets_against_its_invoice(client):
    _, headers = await _bootstrap_and_login(client)
    today = date.today()

    invoice_id, invoice_total, partner_id = await _issue_customer_invoice(
        client, headers, "Credit Note Customer"
    )
    cn_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice_id}:credit-note",
        headers=headers,
        json={"reason": "Return"},
    )
    assert cn_resp.status_code == 201, cn_resp.text

    resp = await client.get(
        f"/api/v1/payments/subledger/customer/{partner_id}",
        headers=headers,
        params={"date_from": str(today), "date_to": str(today)},
    )
    body = resp.json()
    movement_types = sorted(line["movement_type"] for line in body["lines"])
    assert movement_types == ["credit_note", "invoice"]
    # The invoice and its full credit note must exactly net to zero.
    assert Decimal(body["closing_balance"]) == Decimal("0.0000")


async def test_vendor_subledger_bill_and_payment(client):
    _, headers = await _bootstrap_and_login(client)
    cash = await _cash_account_id(client, headers)
    today = date.today()

    bill_id, bill_total, vendor_id = await _issue_vendor_bill(client, headers, "Ledger Vendor A")
    await _pay(
        client,
        headers,
        partner_id=vendor_id,
        payment_type="vendor",
        payment_date=str(today),
        amount=bill_total,
        account_id=cash,
        target_key="vendor_bill_id",
        target_id=bill_id,
    )

    resp = await client.get(
        f"/api/v1/payments/subledger/vendor/{vendor_id}",
        headers=headers,
        params={"date_from": str(today), "date_to": str(today)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["lines"]) == 2
    assert {line["movement_type"] for line in body["lines"]} == {"bill", "payment"}
    assert Decimal(body["closing_balance"]) == Decimal("0.0000")  # fully paid


async def test_subledgers_reconcile_with_general_ledger_ar_and_ap(client):
    """The one test that matters most: sum every customer's Subledger
    closing balance and assert it equals the General Ledger's own AR
    account balance for the same company/date -- and the same for vendors
    against AP. If these ever disagree, that is a real data-integrity bug,
    not a rounding quirk to explain away."""
    _, headers = await _bootstrap_and_login(client)
    cash = await _cash_account_id(client, headers)
    today = date.today()

    _, _, customer_x = await _issue_customer_invoice(
        client, headers, "Reconcile Customer X", qty="2", unit_price="100.00"
    )
    inv_y_id, inv_y_total, customer_y = await _issue_customer_invoice(
        client, headers, "Reconcile Customer Y", qty="1", unit_price="150.00"
    )
    await _pay(
        client,
        headers,
        partner_id=customer_y,
        payment_type="customer",
        payment_date=str(today),
        amount=inv_y_total,
        account_id=cash,
        target_key="sales_invoice_id",
        target_id=inv_y_id,
    )

    bill_id, bill_total, vendor_z = await _issue_vendor_bill(client, headers, "Reconcile Vendor Z")

    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    ar_account_id = next(a["id"] for a in accounts if a["code"] == "1200")
    ap_account_id = next(a["id"] for a in accounts if a["code"] == "2100")

    ar_gl = (
        await client.get(
            "/api/v1/accounting/reports/general-ledger",
            headers=headers,
            params={"account_id": ar_account_id, "date_from": str(today), "date_to": str(today)},
        )
    ).json()
    ap_gl = (
        await client.get(
            "/api/v1/accounting/reports/general-ledger",
            headers=headers,
            params={"account_id": ap_account_id, "date_from": str(today), "date_to": str(today)},
        )
    ).json()

    sub_x = (
        await client.get(
            f"/api/v1/payments/subledger/customer/{customer_x}",
            headers=headers,
            params={"date_from": str(today), "date_to": str(today)},
        )
    ).json()
    sub_y = (
        await client.get(
            f"/api/v1/payments/subledger/customer/{customer_y}",
            headers=headers,
            params={"date_from": str(today), "date_to": str(today)},
        )
    ).json()
    sub_z = (
        await client.get(
            f"/api/v1/payments/subledger/vendor/{vendor_z}",
            headers=headers,
            params={"date_from": str(today), "date_to": str(today)},
        )
    ).json()

    sum_customer_subledgers = Decimal(sub_x["closing_balance"]) + Decimal(sub_y["closing_balance"])
    sum_vendor_subledgers = Decimal(sub_z["closing_balance"])

    assert sum_customer_subledgers == Decimal(ar_gl["closing_balance"])
    assert sum_vendor_subledgers == Decimal(ap_gl["closing_balance"])


async def test_ar_aging_surfaces_open_invoice_for_correct_customer(client):
    _, headers = await _bootstrap_and_login(client)
    today = date.today()
    invoice_id, invoice_total, partner_id = await _issue_customer_invoice(
        client, headers, "Aging Customer"
    )

    resp = await client.get(
        "/api/v1/payments/aging/ar", headers=headers, params={"as_of_date": str(today)}
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    row = next(r for r in rows if r["document_id"] == invoice_id)
    assert row["partner_name"] == "Aging Customer"
    assert Decimal(row["balance_due"]) == Decimal(invoice_total)
    assert row["bucket"] == "current"  # dated today, 0 days overdue as of today


async def test_ar_aging_excludes_fully_credit_noted_invoice(client):
    """Regression test for a real bug found during this Milestone's own
    live verification: AR Aging originally computed an invoice's
    balance_due from payment allocations only, ignoring that a full credit
    note against that same invoice also settles it -- an invoice that was
    entirely credited still showed its full original amount as overdue.
    Fixed in SubledgerService.ar_aging (see the credited_by_original_invoice
    map); this test is what would have caught it before it ever reached
    the Owner Acceptance environment."""
    _, headers = await _bootstrap_and_login(client)
    today = date.today()
    invoice_id, _, partner_id = await _issue_customer_invoice(
        client, headers, "Fully Credited Customer"
    )
    cn_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice_id}:credit-note",
        headers=headers,
        json={"reason": "Full return"},
    )
    assert cn_resp.status_code == 201, cn_resp.text

    resp = await client.get(
        "/api/v1/payments/aging/ar", headers=headers, params={"as_of_date": str(today)}
    )
    rows = resp.json()["rows"]
    assert all(
        r["document_id"] != invoice_id for r in rows
    )  # fully credited -- must not appear as overdue


async def test_ap_aging_excludes_fully_paid_bills(client):
    _, headers = await _bootstrap_and_login(client)
    cash = await _cash_account_id(client, headers)
    today = date.today()
    bill_id, bill_total, vendor_id = await _issue_vendor_bill(client, headers, "Paid Vendor")
    await _pay(
        client,
        headers,
        partner_id=vendor_id,
        payment_type="vendor",
        payment_date=str(today),
        amount=bill_total,
        account_id=cash,
        target_key="vendor_bill_id",
        target_id=bill_id,
    )

    resp = await client.get(
        "/api/v1/payments/aging/ap", headers=headers, params={"as_of_date": str(today)}
    )
    rows = resp.json()["rows"]
    assert all(r["document_id"] != bill_id for r in rows)  # fully paid -- must not appear


def test_aging_bucket_boundaries():
    """Direct unit test of the pure bucketing function -- invoice/bill
    dates are always date.today() in this codebase (no API exists to
    backdate one), so bucket-boundary math at 30/31/60/61/90/91 days can
    only be exercised this way, not through a real overdue document."""
    as_of = date(2026, 6, 30)

    def bucket_for(days_before: int) -> str:
        due = as_of - timedelta(days=days_before)
        row = _aging_row(
            partner=None,
            document_id="00000000-0000-0000-0000-000000000001",
            number="X",
            due_date=due,
            fallback_date=due,
            balance_due=Decimal("100"),
            as_of_date=as_of,
        )
        return row["bucket"]

    assert bucket_for(0) == "current"
    assert bucket_for(30) == "1_30"
    assert bucket_for(31) == "31_60"
    assert bucket_for(60) == "31_60"
    assert bucket_for(61) == "61_90"
    assert bucket_for(90) == "61_90"
    assert bucket_for(91) == "over_90"


async def test_journal_entry_exposes_source_document_for_drilldown(client):
    """Proves the traceability chain General Ledger -> Journal Entry ->
    real source document is real, not just a schema field that's always
    null."""
    _, headers = await _bootstrap_and_login(client)
    invoice_id, _, _ = await _issue_customer_invoice(client, headers, "Traceability Customer")

    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    ar_account_id = next(a["id"] for a in accounts if a["code"] == "1200")
    today = date.today()

    gl = (
        await client.get(
            "/api/v1/accounting/reports/general-ledger",
            headers=headers,
            params={"account_id": ar_account_id, "date_from": str(today), "date_to": str(today)},
        )
    ).json()
    line = next(gl_line for gl_line in gl["lines"] if gl_line["source_table"] == "sales_invoice")
    assert str(line["source_id"]) == invoice_id

    je_detail = (
        await client.get(
            f"/api/v1/accounting/journal-entries/{line['journal_entry_id']}", headers=headers
        )
    ).json()
    assert je_detail["entry"]["source_table"] == "sales_invoice"
    assert je_detail["entry"]["source_id"] == invoice_id


async def test_subledgers_isolated_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client)
    _, _, partner_id = await _issue_customer_invoice(client, headers_a, "Isolation Customer")

    _, headers_b = await _bootstrap_and_login(client)  # unrelated company
    today = date.today()

    resp = await client.get(
        f"/api/v1/payments/subledger/customer/{partner_id}",
        headers=headers_b,
        params={"date_from": str(today), "date_to": str(today)},
    )
    assert resp.status_code == 404  # company B cannot see company A's customer at all

    aging_resp = await client.get(
        "/api/v1/payments/aging/ar", headers=headers_b, params={"as_of_date": str(today)}
    )
    assert aging_resp.json()["rows"] == []


async def test_unapproved_vendor_bill_never_appears_in_subledger_or_aging(client):
    """Documents a real, pre-existing gap found while building this
    Milestone (not introduced by it): `POST /purchasing/vendor-bills`
    creates a bill in 'matched' status without posting any Journal Entry —
    only `:approve` does that (see `VendorBillService.approve_and_post`).
    Nothing in the current Payments module stops a payment being recorded
    against a bill that was never approved. The Subledger's own design
    (only counting movements that actually have a `journal_entry_id`) is
    what keeps THIS report correct regardless — an unapproved bill has no
    real accounting impact yet, so it correctly does not appear here or in
    AP Aging, protecting this Milestone's own reconciliation guarantee even
    though the underlying gap in Payments/Purchasing is unresolved."""
    _, headers = await _bootstrap_and_login(client)
    await _ensure_default_warehouse(client, headers)
    vendor_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "Unapproved Bill Vendor", "is_vendor": True},
    )
    vendor_id = vendor_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Widget", "sales_price": "50.00"},
    )
    product_id = product_resp.json()["id"]
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "order_date": str(date.today()),
            "lines": [
                {
                    "product_id": product_id,
                    "qty": "1",
                    "unit_price": "50.00",
                    "tax_rate_id": TAX_RATE_PLACEHOLDER,
                }
            ],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "1"}]},
    )
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "1", "unit_price": "50.00"}]},
    )
    bill = bill_resp.json()
    assert bill["status"] != "posted"  # confirmed: never approved, so never posted

    today = date.today()
    resp = await client.get(
        f"/api/v1/payments/subledger/vendor/{vendor_id}",
        headers=headers,
        params={"date_from": str(today), "date_to": str(today)},
    )
    assert resp.json()["lines"] == []  # correctly absent -- no real accounting impact yet

    aging = (
        await client.get(
            "/api/v1/payments/aging/ap", headers=headers, params={"as_of_date": str(today)}
        )
    ).json()
    assert all(row["document_id"] != bill["id"] for row in aging["rows"])


async def test_subledger_and_aging_require_permission(client):
    resp = await client.get("/api/v1/payments/aging/ar", params={"as_of_date": str(date.today())})
    assert resp.status_code == 401


async def test_customer_subledger_and_ar_aging_export_pdf_and_excel(client):
    """Standard Reporting Framework — Payments' subledger/aging reports
    must also serve real PDF/Excel, matching every other report."""
    _, headers = await _bootstrap_and_login(client)
    today = date.today()
    _invoice_id, _invoice_total, partner_id = await _issue_customer_invoice(
        client, headers, "Export Customer"
    )

    sub_pdf = await client.get(
        f"/api/v1/payments/subledger/customer/{partner_id}",
        headers=headers,
        params={"date_from": str(today), "date_to": str(today), "format": "pdf"},
    )
    assert sub_pdf.status_code == 200
    assert sub_pdf.headers["content-type"] == "application/pdf"
    assert sub_pdf.content[:4] == b"%PDF"

    sub_xlsx = await client.get(
        f"/api/v1/payments/subledger/vendor/{partner_id}",
        headers=headers,
        params={"date_from": str(today), "date_to": str(today), "format": "xlsx", "lang": "en"},
    )
    assert sub_xlsx.status_code == 200
    assert sub_xlsx.content[:2] == b"PK"

    aging_pdf = await client.get(
        "/api/v1/payments/aging/ar",
        headers=headers,
        params={"as_of_date": str(today), "format": "pdf"},
    )
    assert aging_pdf.status_code == 200
    assert aging_pdf.content[:4] == b"%PDF"

    aging_xlsx = await client.get(
        "/api/v1/payments/aging/ap",
        headers=headers,
        params={"as_of_date": str(today), "format": "xlsx"},
    )
    assert aging_xlsx.status_code == 200
    assert aging_xlsx.content[:2] == b"PK"
