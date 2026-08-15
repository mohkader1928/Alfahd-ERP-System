"""P0-C (Phase-One closure): the audit found sales-invoice issuance, sales
credit notes, and Fixed-Asset depreciation/disposal produced no audit
trail at all. Reuses the existing AuditLogRepository/AuditLog
infrastructure (already used for journal-entry status transitions and
chart-of-accounts edits) rather than a parallel system — see the
`await AuditLogRepository(db).record(...)` call sites in
sales/api/routes.py and fixed_assets/api/routes.py.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client, label="P0C"):
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


async def _issue_invoice(client, headers) -> dict:
    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "P0C Test Customer", "is_customer": True},
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"P0C-{unique_vat()[:8]}", "name": "P0C Test Product", "sales_price": "100.00"},
    )
    product_id = product_resp.json()["id"]
    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-08-01",
            "lines": [
                {"product_id": product_id, "qty": "2", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}
            ],
        },
    )
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)).json()[
        "id"
    ]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    return invoice_resp.json()["invoice"]


async def _get_account(client, headers, code: str) -> dict:
    resp = await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)
    return next(a for a in resp.json() if a["code"] == code)


async def _standard_asset_payload(client, headers, **overrides) -> dict:
    fixed = await _get_account(client, headers, "1410")
    accum = await _get_account(client, headers, "1490")
    expense = await _get_account(client, headers, "5950")
    cash = await _get_account(client, headers, "1100")
    payload = {
        "name": "P0C Test Truck",
        "name_ar": "شاحنة اختبار",
        "fixed_asset_account_id": fixed["id"],
        "accumulated_depreciation_account_id": accum["id"],
        "depreciation_expense_account_id": expense["id"],
        "funding_account_id": cash["id"],
        "acquisition_date": "2026-01-01",
        "cost": "1200.00",
        "salvage_value": "0",
        "useful_life_months": 12,
    }
    payload.update(overrides)
    return payload


async def test_invoice_issuance_creates_audit_entry(client):
    _, headers = await _bootstrap_and_login(client, "P0C-Invoice")
    invoice = await _issue_invoice(client, headers)

    audit_resp = await client.get(
        "/api/v1/identity/audit-log", headers=headers, params={"target_table": "sales_invoice"}
    )
    assert audit_resp.status_code == 200, audit_resp.text
    entries = [e for e in audit_resp.json() if e["target_id"] == invoice["id"]]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["field_name"] == "status"
    assert entry["old_value"] is None
    assert entry["new_value"] == invoice["status"]
    assert entry["user_id"] is not None
    assert entry["changed_at"] is not None


async def test_credit_note_creates_audit_entry(client):
    _, headers = await _bootstrap_and_login(client, "P0C-CreditNote")
    invoice = await _issue_invoice(client, headers)

    credit_note_resp = await client.post(
        f"/api/v1/sales/invoices/{invoice['id']}:credit-note",
        headers=headers,
        json={"reason": "P0C audit test — damaged goods"},
    )
    assert credit_note_resp.status_code == 201, credit_note_resp.text
    credit_note = credit_note_resp.json()["invoice"]

    audit_resp = await client.get(
        "/api/v1/identity/audit-log", headers=headers, params={"target_table": "sales_invoice"}
    )
    entries = [e for e in audit_resp.json() if e["target_id"] == credit_note["id"]]
    assert len(entries) == 1
    assert entries[0]["field_name"] == "status"
    assert entries[0]["old_value"] is None


async def test_freeform_credit_note_creates_audit_entry(client):
    _, headers = await _bootstrap_and_login(client, "P0C-Return")
    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "P0C Return Customer", "is_customer": True},
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"P0CR-{unique_vat()[:8]}", "name": "P0C Return Product", "sales_price": "50.00"},
    )
    product_id = product_resp.json()["id"]

    return_resp = await client.post(
        "/api/v1/sales/invoices:return",
        headers=headers,
        json={
            "partner_id": partner_id,
            "reason": "P0C audit test — freeform return",
            "restock": False,
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "50.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert return_resp.status_code == 201, return_resp.text
    credit_note = return_resp.json()["invoice"]

    audit_resp = await client.get(
        "/api/v1/identity/audit-log", headers=headers, params={"target_table": "sales_invoice"}
    )
    entries = [e for e in audit_resp.json() if e["target_id"] == credit_note["id"]]
    assert len(entries) == 1
    assert entries[0]["field_name"] == "status"


async def test_depreciation_run_creates_audit_entry_per_asset(client):
    _, headers = await _bootstrap_and_login(client, "P0C-Deprec")
    payload = await _standard_asset_payload(client, headers)
    asset_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = asset_resp.json()["id"]

    run_resp = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"}
    )
    assert run_resp.status_code == 200, run_resp.text
    assert run_resp.json()["assets_posted"] == 1

    audit_resp = await client.get(
        "/api/v1/identity/audit-log", headers=headers, params={"target_table": "fixed_asset"}
    )
    entries = [e for e in audit_resp.json() if e["target_id"] == asset_id and e["field_name"] == "depreciation_posted"]
    assert len(entries) == 1
    assert "100.0000" in entries[0]["new_value"]  # 1200/12 = 100/month
    assert "2026-01" in entries[0]["new_value"]


async def test_depreciation_run_skips_no_audit_for_already_posted_period(client):
    """A second run for the same period posts nothing new (idempotent per
    period) — it must not fabricate a second audit entry for no-op assets."""
    _, headers = await _bootstrap_and_login(client, "P0C-DeprecSkip")
    payload = await _standard_asset_payload(client, headers)
    asset_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = asset_resp.json()["id"]

    await client.post("/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-01"})
    second_run = await client.post(
        "/api/v1/fixed-assets:run-depreciation", headers=headers, json={"period_month": "2026-01-15"}
    )
    assert second_run.json()["assets_posted"] == 0

    audit_resp = await client.get(
        "/api/v1/identity/audit-log", headers=headers, params={"target_table": "fixed_asset"}
    )
    entries = [e for e in audit_resp.json() if e["target_id"] == asset_id and e["field_name"] == "depreciation_posted"]
    assert len(entries) == 1


async def test_disposal_creates_audit_entry(client):
    _, headers = await _bootstrap_and_login(client, "P0C-Dispose")
    payload = await _standard_asset_payload(client, headers)
    asset_resp = await client.post("/api/v1/fixed-assets", headers=headers, json=payload)
    asset_id = asset_resp.json()["id"]

    gain_loss_account = await _get_account(client, headers, "4900")
    dispose_resp = await client.post(
        f"/api/v1/fixed-assets/{asset_id}:dispose",
        headers=headers,
        json={"disposal_date": "2026-03-01", "proceeds": "0", "gain_loss_account_id": gain_loss_account["id"]},
    )
    assert dispose_resp.status_code == 200, dispose_resp.text

    audit_resp = await client.get(
        "/api/v1/identity/audit-log", headers=headers, params={"target_table": "fixed_asset"}
    )
    entries = [e for e in audit_resp.json() if e["target_id"] == asset_id and e["field_name"] == "disposed_at"]
    assert len(entries) == 1
    assert entries[0]["new_value"] == "2026-03-01"
    assert entries[0]["old_value"] is None


async def test_audit_log_isolated_across_companies(client):
    """Verify company isolation (P0-C requirement): Company A's audit
    entries must never be visible through Company B's audit-log listing."""
    _, headers_a = await _bootstrap_and_login(client, "P0C-IsoA")
    _, headers_b = await _bootstrap_and_login(client, "P0C-IsoB")

    invoice_a = await _issue_invoice(client, headers_a)
    invoice_b = await _issue_invoice(client, headers_b)

    audit_a = await client.get(
        "/api/v1/identity/audit-log", headers=headers_a, params={"target_table": "sales_invoice"}
    )
    audit_b = await client.get(
        "/api/v1/identity/audit-log", headers=headers_b, params={"target_table": "sales_invoice"}
    )

    ids_in_a = {e["target_id"] for e in audit_a.json()}
    ids_in_b = {e["target_id"] for e in audit_b.json()}

    assert invoice_a["id"] in ids_in_a
    assert invoice_a["id"] not in ids_in_b
    assert invoice_b["id"] in ids_in_b
    assert invoice_b["id"] not in ids_in_a
