"""Commercial Performance Stage 2A — Sales Representative master entity.

Covers exactly the approved Stage 2A scope: a new company-scoped
SalesRepresentative master entity (name, code, is_active, commission_rate)
and Partner.default_sales_rep_id as pure master data. No transaction-level
sales_rep_id snapshot, no collection representative, no commission
calculation — those are explicitly out of scope for this stage.
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


async def _create_sales_rep(client, headers, *, name: str = "Ahmed Al-Rashid", code: str = "REP001", commission_rate=None) -> dict:
    payload = {"name": name, "code": code}
    if commission_rate is not None:
        payload["commission_rate"] = commission_rate
    resp = await client.post("/api/v1/identity/sales-representatives", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_sales_representative_creation_and_reload(client):
    """TEST 1: creation and reload."""
    _, headers = await _bootstrap_and_login(client, f"SRep-Create-{unique_vat()[:6]}")

    created = await _create_sales_rep(client, headers, name="Ahmed Al-Rashid", code="REP001", commission_rate="5.00")
    assert created["name"] == "Ahmed Al-Rashid"
    assert created["code"] == "REP001"
    assert created["is_active"] is True
    assert created["commission_rate"] == "5.00"

    reloaded = (
        await client.get(f"/api/v1/identity/sales-representatives/{created['id']}", headers=headers)
    ).json()
    assert reloaded["name"] == "Ahmed Al-Rashid"
    assert reloaded["code"] == "REP001"
    assert reloaded["commission_rate"] == "5.00"

    listed = (await client.get("/api/v1/identity/sales-representatives", headers=headers)).json()
    assert any(r["id"] == created["id"] for r in listed)


async def test_sales_representative_update(client):
    """TEST 2: update — including deactivation (no hard delete)."""
    _, headers = await _bootstrap_and_login(client, f"SRep-Update-{unique_vat()[:6]}")
    created = await _create_sales_rep(client, headers, code="REP002")

    update_resp = await client.patch(
        f"/api/v1/identity/sales-representatives/{created['id']}",
        headers=headers,
        json={"name": "Mohamed Al-Otaibi", "code": "REP002B", "commission_rate": "7.50", "is_active": False},
    )
    assert update_resp.status_code == 200, update_resp.text
    body = update_resp.json()
    assert body["name"] == "Mohamed Al-Otaibi"
    assert body["code"] == "REP002B"
    assert body["commission_rate"] == "7.50"
    assert body["is_active"] is False

    reloaded = (
        await client.get(f"/api/v1/identity/sales-representatives/{created['id']}", headers=headers)
    ).json()
    assert reloaded["is_active"] is False
    assert reloaded["name"] == "Mohamed Al-Otaibi"


async def test_sales_representative_code_must_be_unique_per_company(client):
    _, headers = await _bootstrap_and_login(client, f"SRep-Dup-{unique_vat()[:6]}")
    await _create_sales_rep(client, headers, code="REP-DUP")
    dup_resp = await client.post(
        "/api/v1/identity/sales-representatives", headers=headers, json={"name": "Someone Else", "code": "REP-DUP"}
    )
    assert dup_resp.status_code == 422, dup_resp.text


async def test_sales_representative_company_isolation(client):
    """TEST 3/4: a rep created in company A is invisible from company B,
    and cross-company GET/PATCH are both correctly rejected (RLS
    company_isolation, same pattern as every other master-data table)."""
    _, headers_a = await _bootstrap_and_login(client, f"SRep-Iso-A-{unique_vat()[:6]}")
    _, headers_b = await _bootstrap_and_login(client, f"SRep-Iso-B-{unique_vat()[:6]}")

    created = await _create_sales_rep(client, headers_a, code="REP-ISO")

    cross_get = await client.get(f"/api/v1/identity/sales-representatives/{created['id']}", headers=headers_b)
    assert cross_get.status_code == 404

    cross_update = await client.patch(
        f"/api/v1/identity/sales-representatives/{created['id']}",
        headers=headers_b,
        json={"name": "Hijacked", "code": "REP-ISO", "is_active": True},
    )
    assert cross_update.status_code == 404

    listed_b = (await client.get("/api/v1/identity/sales-representatives", headers=headers_b)).json()
    assert all(r["id"] != created["id"] for r in listed_b)


async def test_partner_default_sales_rep_save_and_reload(client):
    """TEST 5: Partner.default_sales_rep_id save and reload."""
    _, headers = await _bootstrap_and_login(client, f"Partner-SRep-{unique_vat()[:6]}")
    rep = await _create_sales_rep(client, headers, code="REP-P1")

    create_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "Customer With Rep", "is_customer": True, "default_sales_rep_id": rep["id"]},
    )
    assert create_resp.status_code == 201, create_resp.text
    partner = create_resp.json()
    assert partner["default_sales_rep_id"] == rep["id"]

    reloaded = (await client.get(f"/api/v1/identity/partners/{partner['id']}", headers=headers)).json()
    assert reloaded["default_sales_rep_id"] == rep["id"]


async def test_partner_update_changing_default_representative(client):
    """TEST 6: reassigning the default rep updates master data cleanly."""
    _, headers = await _bootstrap_and_login(client, f"Partner-Reassign-{unique_vat()[:6]}")
    rep_ahmed = await _create_sales_rep(client, headers, name="Ahmed", code="REP-A")
    rep_mohamed = await _create_sales_rep(client, headers, name="Mohamed", code="REP-M")

    partner = (
        await client.post(
            "/api/v1/identity/partners",
            headers=headers,
            json={"name": "Reassign Customer", "is_customer": True, "default_sales_rep_id": rep_ahmed["id"]},
        )
    ).json()
    assert partner["default_sales_rep_id"] == rep_ahmed["id"]

    update_resp = await client.patch(
        f"/api/v1/identity/partners/{partner['id']}",
        headers=headers,
        json={"name": "Reassign Customer", "is_customer": True, "default_sales_rep_id": rep_mohamed["id"]},
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["default_sales_rep_id"] == rep_mohamed["id"]

    reloaded = (await client.get(f"/api/v1/identity/partners/{partner['id']}", headers=headers)).json()
    assert reloaded["default_sales_rep_id"] == rep_mohamed["id"]

    # Clearing it back to none must also work (not a one-way assignment).
    clear_resp = await client.patch(
        f"/api/v1/identity/partners/{partner['id']}",
        headers=headers,
        json={"name": "Reassign Customer", "is_customer": True, "default_sales_rep_id": None},
    )
    assert clear_resp.status_code == 200, clear_resp.text
    assert clear_resp.json()["default_sales_rep_id"] is None


async def test_partner_rejects_sales_rep_from_another_company(client):
    """TEST 7: cross-company FK assignment is rejected, both at create and
    at update time — same-company validation, mirroring _validate_parent."""
    _, headers_a = await _bootstrap_and_login(client, f"CrossCo-A-{unique_vat()[:6]}")
    _, headers_b = await _bootstrap_and_login(client, f"CrossCo-B-{unique_vat()[:6]}")

    rep_in_b = await _create_sales_rep(client, headers_b, code="REP-B-ONLY")

    create_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers_a,
        json={"name": "Cross Co Customer", "is_customer": True, "default_sales_rep_id": rep_in_b["id"]},
    )
    assert create_resp.status_code == 422, create_resp.text

    partner_a = (
        await client.post(
            "/api/v1/identity/partners", headers=headers_a, json={"name": "Plain A Customer", "is_customer": True}
        )
    ).json()
    update_resp = await client.patch(
        f"/api/v1/identity/partners/{partner_a['id']}",
        headers=headers_a,
        json={"name": "Plain A Customer", "is_customer": True, "default_sales_rep_id": rep_in_b["id"]},
    )
    assert update_resp.status_code == 422, update_resp.text


async def test_existing_partners_with_null_default_sales_rep_remain_valid(client):
    """TEST 8: a partner created with no sales rep at all keeps working
    exactly as before this stage — API backward compatibility."""
    _, headers = await _bootstrap_and_login(client, f"NullRep-{unique_vat()[:6]}")
    resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "No Rep Customer", "is_customer": True}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["default_sales_rep_id"] is None

    reloaded = (await client.get(f"/api/v1/identity/partners/{resp.json()['id']}", headers=headers)).json()
    assert reloaded["default_sales_rep_id"] is None


async def test_sales_workflow_unaffected_for_customer_with_no_sales_rep(client):
    """TEST 9: existing sales/accounting workflows remain unaffected — a
    full quotation -> order -> invoice flow for a customer with no
    default_sales_rep_id still issues cleanly (no transaction-level field
    exists yet in this stage, so this just proves no regression)."""
    _, headers = await _bootstrap_and_login(client, f"Unaffected-{unique_vat()[:6]}")
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Unaffected Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{unique_vat()[:8]}", "name": "Unaffected Product", "sales_price": "500.00"},
    )
    product_id = product_resp.json()["id"]

    quote = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "500.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    assert quote.status_code == 201, quote.text
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201, invoice_resp.text
    assert invoice_resp.json()["invoice"]["total_amount"] == "575.00"
