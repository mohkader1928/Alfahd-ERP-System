"""Commercial Performance Stage 3 (Phase 1) — commission ledger + Dashboard/
Reporting readiness.

Covers: sales commission on invoice issuance (pre-tax subtotal, not VAT),
historical rate preservation when SalesRepresentative.commission_rate later
changes, credit-note reversal using the ORIGINAL invoice's stored rate
(never today's), proportional collection commission on (partial) customer
payments, independence of sales vs. collection commission, vendor-payment
exclusion, unattributed/legacy transactions surfaced separately (never
merged or guessed), multi-company isolation, a rep with no commission_rate
configured getting no commission row, and Dashboard/report reconciliation.

No commission settlement, no GL posting, no payroll — explicitly out of
scope for this stage.
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


async def _cash_account_id(client, headers) -> str:
    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    return next(a["id"] for a in accounts if a["code"] == "1100")


async def _create_sales_rep(
    client, headers, *, name: str = "Ahmed", code: str = "REP001", commission_rate: str | None = "5.00"
) -> dict:
    payload = {"name": name, "code": code}
    if commission_rate is not None:
        payload["commission_rate"] = commission_rate
    resp = await client.post("/api/v1/identity/sales-representatives", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _update_sales_rep_rate(client, headers, rep: dict, *, commission_rate: str) -> dict:
    resp = await client.patch(
        f"/api/v1/identity/sales-representatives/{rep['id']}",
        headers=headers,
        json={"name": rep["name"], "code": rep["code"], "commission_rate": commission_rate, "is_active": True},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_customer(client, headers, *, name: str = "Customer") -> str:
    resp = await client.post("/api/v1/identity/partners", headers=headers, json={"name": name, "is_customer": True})
    return resp.json()["id"]


async def _issue_customer_invoice(
    client, headers, *, partner_id: str, sales_rep_id: str | None = None, unit_price: str = "100.00", invoice_date: str = "2026-06-01"
) -> dict:
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Stage3 Widget", "sales_price": unit_price},
    )
    product_id = product_resp.json()["id"]

    quote_payload = {
        "partner_id": partner_id,
        "quote_date": invoice_date,
        "lines": [{"product_id": product_id, "qty": "1", "unit_price": unit_price, "tax_rate_id": TAX_RATE_PLACEHOLDER}],
    }
    if sales_rep_id is not None:
        quote_payload["sales_rep_id"] = sales_rep_id
    quote_resp = await client.post("/api/v1/sales/quotations", headers=headers, json=quote_payload)
    assert quote_resp.status_code == 201, quote_resp.text
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text
    return invoice_resp.json()["invoice"]


async def _by_representative(client, headers, *, date_from="2026-01-01", date_to="2026-12-31") -> list[dict]:
    resp = await client.get(
        "/api/v1/reporting/commercial/by-representative",
        headers=headers,
        params={"date_from": date_from, "date_to": date_to},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _rep_row(rows: list[dict], representative_id: str | None) -> dict:
    return next(r for r in rows if r["representative_id"] == representative_id)


async def test_sales_commission_calculated_on_pretax_subtotal_at_invoice_issuance(client):
    _, headers = await _bootstrap_and_login(client, f"S3-Calc-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers, commission_rate="10.00")
    partner_id = await _create_customer(client, headers)
    invoice = await _issue_customer_invoice(client, headers, partner_id=partner_id, sales_rep_id=rep["id"], unit_price="100.00")
    assert Decimal(invoice["subtotal_amount"]) == Decimal("100.00")
    assert Decimal(invoice["total_amount"]) > Decimal("100.00")  # VAT included in total, not in subtotal

    rows = await _by_representative(client, headers)
    row = await _rep_row(rows, rep["id"])
    assert Decimal(row["gross_sales"]) == Decimal("100.00")
    # 10% of the pre-tax subtotal (100.00), not of the VAT-inclusive total.
    assert Decimal(row["sales_commission"]) == Decimal("10.00")

    detail = (
        await client.get(
            f"/api/v1/reporting/commercial/representatives/{rep['id']}/performance",
            headers=headers,
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
    ).json()
    assert len(detail["sales_lines"]) == 1
    assert detail["sales_lines"][0]["invoice_id"] == invoice["id"]
    assert Decimal(detail["sales_lines"][0]["commission_rate"]) == Decimal("10.00")
    assert Decimal(detail["sales_lines"][0]["commission_amount"]) == Decimal("10.00")


async def test_historical_commission_rate_is_never_recalculated_after_rate_change(client):
    """TEST: a January invoice commissioned at 5% must stay 5,000 SAR
    forever, even after the rep's rate later changes to 7%."""
    _, headers = await _bootstrap_and_login(client, f"S3-Hist-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers, commission_rate="5.00")
    partner_id = await _create_customer(client, headers)
    january_invoice = await _issue_customer_invoice(
        client, headers, partner_id=partner_id, sales_rep_id=rep["id"], unit_price="100000.00", invoice_date="2026-01-15"
    )

    await _update_sales_rep_rate(client, headers, rep, commission_rate="7.00")

    march_invoice = await _issue_customer_invoice(
        client, headers, partner_id=partner_id, sales_rep_id=rep["id"], unit_price="50000.00", invoice_date="2026-03-15"
    )

    detail = (
        await client.get(
            f"/api/v1/reporting/commercial/representatives/{rep['id']}/performance",
            headers=headers,
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
    ).json()
    by_invoice = {line["invoice_id"]: line for line in detail["sales_lines"]}
    assert Decimal(by_invoice[january_invoice["id"]]["commission_rate"]) == Decimal("5.00")
    assert Decimal(by_invoice[january_invoice["id"]]["commission_amount"]) == Decimal("5000.00")
    assert Decimal(by_invoice[march_invoice["id"]]["commission_rate"]) == Decimal("7.00")
    assert Decimal(by_invoice[march_invoice["id"]]["commission_amount"]) == Decimal("3500.00")


async def test_credit_note_reverses_commission_using_the_original_invoice_rate(client):
    """TEST: a credit note against an invoice must reverse commission at
    the rate the ORIGINAL sale was commissioned at, not today's rate — so
    the reversal exactly offsets what was actually paid out."""
    _, headers = await _bootstrap_and_login(client, f"S3-CN-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers, commission_rate="5.00")
    partner_id = await _create_customer(client, headers)
    invoice = await _issue_customer_invoice(
        client, headers, partner_id=partner_id, sales_rep_id=rep["id"], unit_price="20000.00", invoice_date="2026-01-10"
    )

    await _update_sales_rep_rate(client, headers, rep, commission_rate="7.00")

    cn_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice['id']}:credit-note",
        headers=headers,
        json={"reason": "Stage3 test return", "restock": False},
    )
    assert cn_resp.status_code == 201, cn_resp.text

    detail = (
        await client.get(
            f"/api/v1/reporting/commercial/representatives/{rep['id']}/performance",
            headers=headers,
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
    ).json()
    assert len(detail["returns_lines"]) == 1
    return_line = detail["returns_lines"][0]
    assert return_line["original_invoice_number"] == invoice["number"]
    # Reversal uses the ORIGINAL 5% rate, not the current 7% rate.
    assert Decimal(return_line["commission_rate"]) == Decimal("5.00")
    assert Decimal(return_line["commission_amount"]) == Decimal("-1000.00")

    rows = await _by_representative(client, headers)
    row = await _rep_row(rows, rep["id"])
    assert Decimal(row["returns"]) == Decimal("20000.00")
    assert Decimal(row["net_sales"]) == Decimal("0.00")
    # 1000 (sales) - 1000 (reversal) = 0 net commission, not 20000*7%-based.
    assert Decimal(row["sales_commission"]) == Decimal("0.00")


async def test_partial_payments_generate_proportional_collection_commission(client):
    _, headers = await _bootstrap_and_login(client, f"S3-Partial-{unique_vat()[:6]}")
    collector = await _create_sales_rep(client, headers, name="Sara", code="REP-COL", commission_rate="10.00")
    cash_id = await _cash_account_id(client, headers)
    partner_id = await _create_customer(client, headers)
    invoice = await _issue_customer_invoice(client, headers, partner_id=partner_id, unit_price="1000.00")
    total = invoice["total_amount"]
    half = str((Decimal(total) / 2).quantize(Decimal("0.01")))
    remainder = str(Decimal(total) - Decimal(half))

    for amount in (half, remainder):
        resp = await client.post(
            "/api/v1/payments/payments",
            headers=headers,
            json={
                "partner_id": partner_id,
                "payment_type": "customer",
                "payment_date": "2026-06-05",
                "amount": amount,
                "account_id": cash_id,
                "collection_rep_id": collector["id"],
                "allocations": [{"sales_invoice_id": invoice["id"], "amount": amount}],
            },
        )
        assert resp.status_code == 201, resp.text

    rows = await _by_representative(client, headers)
    row = await _rep_row(rows, collector["id"])
    assert Decimal(row["collections"]) == Decimal(total)
    expected_commission = (Decimal(total) * Decimal("10.00") / Decimal("100")).quantize(Decimal("0.01"))
    assert Decimal(row["collection_commission"]) == expected_commission

    detail = (
        await client.get(
            f"/api/v1/reporting/commercial/representatives/{collector['id']}/performance",
            headers=headers,
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
    ).json()
    assert len(detail["collections_lines"]) == 2
    line_commissions = sorted(Decimal(line["commission_amount"]) for line in detail["collections_lines"])
    assert sum(line_commissions) == expected_commission


async def test_sales_commission_and_collection_commission_are_independent(client):
    _, headers = await _bootstrap_and_login(client, f"S3-Indep-{unique_vat()[:6]}")
    seller = await _create_sales_rep(client, headers, name="Ahmed", code="REP-SELL", commission_rate="5.00")
    collector = await _create_sales_rep(client, headers, name="Sara", code="REP-COL", commission_rate="8.00")
    cash_id = await _cash_account_id(client, headers)
    partner_id = await _create_customer(client, headers)
    invoice = await _issue_customer_invoice(client, headers, partner_id=partner_id, sales_rep_id=seller["id"], unit_price="1000.00")

    await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": invoice["total_amount"],
            "account_id": cash_id,
            "collection_rep_id": collector["id"],
            "allocations": [{"sales_invoice_id": invoice["id"], "amount": invoice["total_amount"]}],
        },
    )

    rows = await _by_representative(client, headers)
    seller_row = await _rep_row(rows, seller["id"])
    collector_row = await _rep_row(rows, collector["id"])
    assert Decimal(seller_row["sales_commission"]) == Decimal("50.00")  # 5% of the 1000.00 pre-tax subtotal
    assert Decimal(seller_row["collection_commission"]) == Decimal("0")
    assert Decimal(collector_row["sales_commission"]) == Decimal("0")
    # Collection commission is based on the actual VAT-inclusive amount
    # collected (1150.00 = 1000.00 + 15% VAT), not the pre-tax subtotal —
    # unlike sales commission, which is deliberately net-of-VAT.
    expected_collection_commission = (Decimal(invoice["total_amount"]) * Decimal("8.00") / Decimal("100")).quantize(
        Decimal("0.01")
    )
    assert Decimal(collector_row["collection_commission"]) == expected_collection_commission


async def test_vendor_payments_never_generate_collection_commission(client):
    _, headers = await _bootstrap_and_login(client, f"S3-Vendor-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers, commission_rate="10.00")
    cash_id = await _cash_account_id(client, headers)
    vendor_resp = await client.post("/api/v1/identity/partners", headers=headers, json={"name": "Stage3 Vendor", "is_vendor": True})
    vendor_id = vendor_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Stage3 Steel", "sales_price": "50.00"},
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

    # Even if a collection_rep_id is explicitly passed on a VENDOR payment,
    # no collection commission may ever be generated from it.
    resp = await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": vendor_id,
            "payment_type": "vendor",
            "payment_date": "2026-06-05",
            "amount": bill["total_amount"],
            "account_id": cash_id,
            "collection_rep_id": rep["id"],
            "allocations": [{"vendor_bill_id": bill["id"], "amount": bill["total_amount"]}],
        },
    )
    assert resp.status_code == 201, resp.text

    rows = await _by_representative(client, headers)
    row = await _rep_row(rows, rep["id"])
    assert Decimal(row["collections"]) == Decimal("0")
    assert Decimal(row["collection_commission"]) == Decimal("0")


async def test_unattributed_legacy_sales_shown_separately_never_merged(client):
    _, headers = await _bootstrap_and_login(client, f"S3-Legacy-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers, commission_rate="5.00")
    partner_id = await _create_customer(client, headers)
    # No sales_rep_id at all — a legacy/unattributed sale.
    await _issue_customer_invoice(client, headers, partner_id=partner_id, sales_rep_id=None, unit_price="300.00")
    await _issue_customer_invoice(client, headers, partner_id=partner_id, sales_rep_id=rep["id"], unit_price="100.00")

    rows = await _by_representative(client, headers)
    unattributed = await _rep_row(rows, None)
    assert unattributed["is_unattributed"] is True
    assert unattributed["representative_name"] == "Unattributed / Legacy"
    assert Decimal(unattributed["gross_sales"]) == Decimal("300.00")

    rep_row = await _rep_row(rows, rep["id"])
    assert Decimal(rep_row["gross_sales"]) == Decimal("100.00")  # never absorbs the unattributed 300


async def test_representative_with_no_commission_rate_gets_zero_commission_not_error(client):
    _, headers = await _bootstrap_and_login(client, f"S3-NoRate-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers, commission_rate=None)
    partner_id = await _create_customer(client, headers)
    await _issue_customer_invoice(client, headers, partner_id=partner_id, sales_rep_id=rep["id"], unit_price="500.00")

    rows = await _by_representative(client, headers)
    row = await _rep_row(rows, rep["id"])
    assert Decimal(row["gross_sales"]) == Decimal("500.00")
    assert Decimal(row["sales_commission"]) == Decimal("0")


async def test_multi_company_isolation_on_commercial_reports(client):
    _, headers_a = await _bootstrap_and_login(client, f"S3-CoA-{unique_vat()[:6]}")
    _, headers_b = await _bootstrap_and_login(client, f"S3-CoB-{unique_vat()[:6]}")
    rep_a = await _create_sales_rep(client, headers_a, code="REP-A", commission_rate="5.00")
    rep_b = await _create_sales_rep(client, headers_b, code="REP-B", commission_rate="5.00")
    partner_a = await _create_customer(client, headers_a, name="Customer A")
    partner_b = await _create_customer(client, headers_b, name="Customer B")
    await _issue_customer_invoice(client, headers_a, partner_id=partner_a, sales_rep_id=rep_a["id"], unit_price="700.00")
    await _issue_customer_invoice(client, headers_b, partner_id=partner_b, sales_rep_id=rep_b["id"], unit_price="900.00")

    rows_a = await _by_representative(client, headers_a)
    rows_b = await _by_representative(client, headers_b)
    assert {r["representative_id"] for r in rows_a if not r["is_unattributed"]} == {rep_a["id"]}
    assert {r["representative_id"] for r in rows_b if not r["is_unattributed"]} == {rep_b["id"]}
    assert rep_b["id"] not in {r["representative_id"] for r in rows_a}
    assert rep_a["id"] not in {r["representative_id"] for r in rows_b}

    # Cross-company drill-down must 404/empty, never leak.
    cross_resp = await client.get(
        f"/api/v1/reporting/commercial/representatives/{rep_b['id']}/performance",
        headers=headers_a,
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert cross_resp.status_code == 200
    assert cross_resp.json()["summary"] is None
    assert cross_resp.json()["sales_lines"] == []


async def test_dashboard_commercial_kpis_reconcile_with_by_representative_report(client):
    _, headers = await _bootstrap_and_login(client, f"S3-Dash-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers, commission_rate="6.00")
    cash_id = await _cash_account_id(client, headers)
    partner_id = await _create_customer(client, headers)
    invoice = await _issue_customer_invoice(client, headers, partner_id=partner_id, sales_rep_id=rep["id"], unit_price="1000.00")
    await client.post(
        "/api/v1/payments/payments",
        headers=headers,
        json={
            "partner_id": partner_id,
            "payment_type": "customer",
            "payment_date": "2026-06-05",
            "amount": invoice["total_amount"],
            "account_id": cash_id,
            "collection_rep_id": rep["id"],
            "allocations": [{"sales_invoice_id": invoice["id"], "amount": invoice["total_amount"]}],
        },
    )

    # Executive Dashboard redesign: the Dashboard's Commercial Performance
    # section no longer carries its own bundled commercial_* fields — it
    # calls /commercial/by-representative directly (same architecture as
    # Sales Reports and the Representative Performance page), so there is
    # structurally only one Net Sales calculation to reconcile against.
    # /commercial/net-sales-trend must sum to the exact same Net Sales
    # total as /commercial/by-representative for the same range.
    trend = (
        await client.get(
            "/api/v1/reporting/commercial/net-sales-trend",
            headers=headers,
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
    ).json()
    rows = await _by_representative(client, headers)

    trend_net_sales_total = sum((Decimal(p["net_sales"]) for p in trend), Decimal("0"))
    by_rep_net_sales_total = sum((Decimal(r["net_sales"]) for r in rows), Decimal("0"))
    assert trend_net_sales_total == by_rep_net_sales_total

    dashboard = (
        await client.get(
            "/api/v1/reporting/dashboard",
            headers=headers,
            params={"period_start": "2026-01-01", "period_end": "2026-12-31"},
        )
    ).json()
    assert "commercial_total_sales" not in dashboard
    assert "representative_performance" not in dashboard
