"""Integration smoke test for Backend M5 — Reporting.

Exercises FR-RPT-003 (dashboard KPIs, aggregated across Sales/Purchasing/
Accounting — the one module allowed to read across boundaries per Phase 8
§3), FR-RPT-001/002 (CSV export), and FR-RPT-004 (audit log report), plus
verifies the audit-log write points added in this milestone actually
produce rows (the table/repository existed since M0 but nothing wrote to
it until now).
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Rpt Test Holding",
        "company_legal_name": "Rpt Test Trading Co.",
        "company_legal_name_ar": "Rpt Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Rpt Test Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201
    company_id = boot_resp.json()["company_id"]
    branch_id = boot_resp.json()["branch_id"]
    admin_role_id = boot_resp.json()["admin_role_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, headers, admin_role_id


async def test_dashboard_reflects_sales_and_purchases(client):
    _, headers, _ = await _bootstrap_and_login(client)

    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "B2B Buyer", "is_customer": True, "vat_number": unique_vat()},
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Widget", "sales_price": "100.00"},
    )
    product_id = product_resp.json()["id"]

    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    quotation_id = quote_resp.json()["id"]
    order_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    order_id = order_resp.json()["id"]
    await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)

    dashboard_resp = await client.get(
        "/api/v1/reporting/dashboard",
        headers=headers,
        params={"period_start": "2026-01-01", "period_end": "2026-12-31"},
    )
    assert dashboard_resp.status_code == 200
    summary = dashboard_resp.json()
    assert summary["period_sales_total"] == "115.0000"  # 100 + 15% VAT
    assert summary["receivables_balance"] == "115.0000"
    assert summary["period_purchases_total"] == "0.0000"
    assert summary["payables_balance"] == "0.0000"
    assert summary["cash_balance"] == "0.0000"


async def test_dashboard_purchases_excludes_vendor_debit_notes(client):
    """Regression for a real reported bug: the Dashboard's "Purchases" KPI
    summed every posted VendorBill row regardless of `bill_type`, so a
    Vendor Debit Note (a return to the vendor, stored with the same
    positive `total_amount` as the bill it reverses) was ADDED on top of
    the original bill instead of excluded -- roughly doubling the visible
    impact of every return. A bill for 2300 fully returned via debit note
    must still show period_purchases_total == 2300.0000 (the original
    bill only), not 4600."""
    _, headers, _ = await _bootstrap_and_login(client)

    vendor_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Debit Note Vendor", "is_vendor": True}
    )
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"DASH-{unique_vat()[:8]}", "name": "Dashboard Test Product"},
    )
    product_id = product_resp.json()["id"]
    await client.post("/api/v1/inventory/warehouses", headers=headers, json={"name": "Main", "is_default": True})

    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": vendor_resp.json()["id"],
            "order_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "100", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    await client.post(
        f"/api/v1/purchasing/orders/{order_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "100"}]},
    )
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_id}/vendor-bills",
        headers=headers,
        json={"vendor_reference": "INV-1", "lines": [{"purchase_order_line_id": po_line_id, "qty": "100", "unit_price": "20.00"}]},
    )
    bill_id = bill_resp.json()["id"]
    approve_resp = await client.post(f"/api/v1/purchasing/vendor-bills/{bill_id}:approve", headers=headers)
    assert approve_resp.status_code == 200, approve_resp.text
    bill_total = approve_resp.json()["total_amount"]

    dashboard_before = await client.get(
        "/api/v1/reporting/dashboard", headers=headers, params={"period_start": "2026-01-01", "period_end": "2026-12-31"}
    )
    assert dashboard_before.json()["period_purchases_total"] == bill_total

    debit_resp = await client.post(
        f"/api/v1/purchasing/vendor-bills/{bill_id}:debit-note",
        headers=headers,
        json={"reason": "Full return"},
    )
    assert debit_resp.status_code == 201, debit_resp.text

    dashboard_after = await client.get(
        "/api/v1/reporting/dashboard", headers=headers, params={"period_start": "2026-01-01", "period_end": "2026-12-31"}
    )
    # The debit note must not add to the KPI -- purchases stays exactly the
    # original bill's amount, not bill_total * 2.
    assert dashboard_after.json()["period_purchases_total"] == bill_total


# --- P0-8: Dashboard KPIs + fiscal-year-aware chart -----------------------


async def test_dashboard_cash_balance_reflects_manual_journal_entry(client):
    _, headers, _ = await _bootstrap_and_login(client)

    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    cash_id = next(a["id"] for a in accounts if a["code"] == "1100")
    capital_id = next(a["id"] for a in accounts if a["code"] == "3100")

    je_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-01",
            "reference": "Owner capital injection",
            "lines": [
                {"account_id": cash_id, "debit": 5000, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 5000},
            ],
        },
    )
    entry_id = je_resp.json()["id"]
    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert post_resp.status_code == 200

    dashboard_resp = await client.get(
        "/api/v1/reporting/dashboard",
        headers=headers,
        params={"period_start": "2026-01-01", "period_end": "2026-12-31"},
    )
    assert dashboard_resp.status_code == 200
    assert dashboard_resp.json()["cash_balance"] == "5000.0000"


async def test_dashboard_sales_trend_spans_exactly_the_requested_period(client):
    """The trend chart used to be hardcoded to the 6 calendar months
    trailing today, disconnected from the period_start/period_end filter
    driving the KPI cards above it. It must now return exactly one point
    per calendar month within the requested range, whatever that range is
    — proving the chart and the KPIs describe the same period."""
    _, headers, _ = await _bootstrap_and_login(client)

    dashboard_resp = await client.get(
        "/api/v1/reporting/dashboard",
        headers=headers,
        params={"period_start": "2026-03-01", "period_end": "2026-05-31"},
    )
    assert dashboard_resp.status_code == 200
    trend = dashboard_resp.json()["sales_trend"]
    assert [point["period_label"] for point in trend] == ["2026-03", "2026-04", "2026-05"]


async def test_company_fiscal_year_start_month_defaults_to_january_and_is_editable(client):
    company_id, headers, _ = await _bootstrap_and_login(client)

    get_resp = await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)
    assert get_resp.json()["fiscal_year_start_month"] == 1

    patch_resp = await client.patch(
        f"/api/v1/identity/companies/{company_id}",
        headers=headers,
        json={
            "legal_name": "Rpt Test Trading Co.",
            "legal_name_ar": "Rpt Test Trading Arabic",
            "vat_number": unique_vat(),
            "cr_number": None,
            "fiscal_year_start_month": 4,
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["fiscal_year_start_month"] == 4

    get_resp_2 = await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)
    assert get_resp_2.json()["fiscal_year_start_month"] == 4


async def test_export_sales_invoices_returns_csv(client):
    _, headers, _ = await _bootstrap_and_login(client)
    resp = await client.get("/api/v1/reporting/export/sales-invoices", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "number,invoice_type,status" in resp.text


async def test_audit_log_records_journal_entry_posting(client):
    _, headers, _ = await _bootstrap_and_login(client)

    accounts_resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    accounts = accounts_resp.json()
    cash_id = next(a["id"] for a in accounts if a["code"] == "1100")
    capital_id = next(a["id"] for a in accounts if a["code"] == "3100")

    create_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-01",
            "lines": [
                {"account_id": cash_id, "debit": 500, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 500},
            ],
        },
    )
    entry_id = create_resp.json()["id"]
    post_resp = await client.post(f"/api/v1/accounting/journal-entries/{entry_id}:post", headers=headers)
    assert post_resp.status_code == 200

    audit_resp = await client.get(
        "/api/v1/identity/audit-log", headers=headers, params={"target_table": "journal_entry"}
    )
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    assert len(entries) == 1
    assert entries[0]["target_id"] == entry_id
    assert entries[0]["old_value"] == "draft"
    assert entries[0]["new_value"] == "posted"


async def test_audit_log_records_role_assignment(client):
    company_id, headers, admin_role_id = await _bootstrap_and_login(client)

    user_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": unique_email(), "full_name": "New User", "password": "Str0ng!Passw0rd", "company_id": company_id},
    )
    assert user_resp.status_code == 201
    new_user_id = user_resp.json()["id"]

    assign_resp = await client.post(
        f"/api/v1/identity/users/{new_user_id}/roles", headers=headers, json={"role_id": admin_role_id}
    )
    assert assign_resp.status_code == 204

    audit_resp = await client.get(
        "/api/v1/identity/audit-log", headers=headers, params={"target_table": "user_role"}
    )
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    assert len(entries) == 1
    assert entries[0]["target_id"] == new_user_id
    assert entries[0]["new_value"] == admin_role_id


async def test_export_audit_log_returns_csv(client):
    _, headers, _ = await _bootstrap_and_login(client)
    resp = await client.get("/api/v1/reporting/export/audit-log", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")


async def test_reporting_endpoints_require_permission(client):
    resp = await client.get(
        "/api/v1/reporting/dashboard", params={"period_start": "2026-01-01", "period_end": "2026-12-31"}
    )
    assert resp.status_code == 401
