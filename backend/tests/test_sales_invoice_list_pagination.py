"""Integration smoke test for server-side pagination/filtering on the
Sales Invoices list (Product Owner audit): `GET /sales/invoices` used to
hardcode `limit=500` with no `offset`, silently hiding any invoice past
the 500th most recent with no way to reach it — a real data-visibility
bug, not just a missing nice-to-have. Proves the fix: real LIMIT/OFFSET
across multiple pages, a correct `total`, and status/date filters that
actually narrow the server-side query.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Pagination Test Holding",
        "company_legal_name": "Pagination Test Trading Co.",
        "company_legal_name_ar": "Pagination Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Pagination Test Admin",
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


async def _issue_invoice(client, headers, *, invoice_date: str):
    partner = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Pagination Customer", "is_customer": True}
    )
    product = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"PAGE-{unique_vat()[:8]}", "name": "Pagination Product", "sales_price": "10.00"},
    )
    quote = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner.json()["id"],
            "quote_date": invoice_date,
            "lines": [{"product_id": product.json()["id"], "qty": "1", "unit_price": "10.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    return invoice_resp.json()["invoice"]


async def test_pagination_returns_distinct_pages_and_correct_total(client):
    _, headers = await _bootstrap_and_login(client)
    invoices = [await _issue_invoice(client, headers, invoice_date="2026-06-01") for _ in range(5)]
    invoice_ids = {inv["id"] for inv in invoices}

    page1 = (await client.get("/api/v1/sales/invoices", headers=headers, params={"page": 1, "page_size": 2})).json()
    assert page1["total"] == 5
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert len(page1["items"]) == 2

    page2 = (await client.get("/api/v1/sales/invoices", headers=headers, params={"page": 2, "page_size": 2})).json()
    assert len(page2["items"]) == 2

    page3 = (await client.get("/api/v1/sales/invoices", headers=headers, params={"page": 3, "page_size": 2})).json()
    assert len(page3["items"]) == 1

    # No overlap between pages, and every invoice is reachable across the
    # three pages -- this is the actual regression check for the old
    # hardcoded-limit-with-no-offset bug.
    seen_ids = {inv["id"] for inv in page1["items"] + page2["items"] + page3["items"]}
    assert seen_ids == invoice_ids


async def test_status_filter_narrows_results(client):
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_invoice(client, headers, invoice_date="2026-06-01")

    matching = (
        await client.get("/api/v1/sales/invoices", headers=headers, params={"status": invoice["status"]})
    ).json()
    assert any(inv["id"] == invoice["id"] for inv in matching["items"])

    non_matching = (
        await client.get("/api/v1/sales/invoices", headers=headers, params={"status": "draft"})
    ).json()
    assert non_matching["total"] == 0
    assert non_matching["items"] == []


async def test_date_range_filter_narrows_results(client):
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_invoice(client, headers, invoice_date="2026-06-01")

    in_range = (
        await client.get(
            "/api/v1/sales/invoices",
            headers=headers,
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
    ).json()
    assert any(inv["id"] == invoice["id"] for inv in in_range["items"])

    out_of_range = (
        await client.get(
            "/api/v1/sales/invoices",
            headers=headers,
            params={"date_from": "2020-01-01", "date_to": "2020-12-31"},
        )
    ).json()
    assert out_of_range["total"] == 0
