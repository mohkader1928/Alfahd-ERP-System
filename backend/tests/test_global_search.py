"""Integration smoke test for Global Search (Professional Workspace Layer).

Every reference ERP has one search box that crosses entity types; this
system had none before this bundle. Mirrors the bootstrap/invoice-creation
pattern in test_sales_reporting_bundle_e.py.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Search Test Holding",
        "company_legal_name": "Search Test Trading Co.",
        "company_legal_name_ar": "Search Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Search Test Admin",
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


async def test_search_finds_partner_and_product_by_name(client):
    _, headers = await _bootstrap_and_login(client)

    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Zephyr Trading LLC", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": "ZEP-001", "name": "Zephyr Widget", "sales_price": "50.00"},
    )
    product_id = product_resp.json()["id"]

    resp = await client.get("/api/v1/reporting/search", headers=headers, params={"q": "Zephyr"})
    assert resp.status_code == 200
    rows = resp.json()
    types_and_ids = {(r["type"], r["id"]) for r in rows}
    assert ("partner", partner_id) in types_and_ids
    assert ("product", product_id) in types_and_ids


async def test_search_finds_sales_invoice_by_number(client):
    _, headers = await _bootstrap_and_login(client)
    partner_resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Search Invoice Customer", "is_customer": True}
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": "SRCH-01", "name": "Search Product", "sales_price": "10.00"},
    )
    product_id = product_resp.json()["id"]
    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "10.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    quotation_id = quote_resp.json()["id"]
    order_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    order_id = order_resp.json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    invoice = invoice_resp.json()["invoice"]

    resp = await client.get("/api/v1/reporting/search", headers=headers, params={"q": invoice["number"]})
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["type"] == "sales_invoice" and r["id"] == invoice["id"] for r in rows)


async def test_search_isolated_across_companies(client):
    _, headers_a = await _bootstrap_and_login(client)
    await client.post(
        "/api/v1/identity/partners", headers=headers_a, json={"name": "CrossCompanySecret Corp", "is_customer": True}
    )

    _, headers_b = await _bootstrap_and_login(client)
    resp = await client.get("/api/v1/reporting/search", headers=headers_b, params={"q": "CrossCompanySecret"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_ignores_short_queries(client):
    _, headers = await _bootstrap_and_login(client)
    resp = await client.get("/api/v1/reporting/search", headers=headers, params={"q": "a"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_requires_permission(client):
    resp = await client.get("/api/v1/reporting/search", params={"q": "test"})
    assert resp.status_code == 401
