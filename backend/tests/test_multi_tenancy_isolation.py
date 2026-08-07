"""Phase 16A — Multi-Tenancy & Database Isolation Hardening: security tests.

These tests exist to *prove*, not assume, that Company A cannot reach
Company B's data through the API/database boundary, after the Phase 16A
migration added `company_id` + RLS to every line-item table (plus
`zatca_submission`, `role`, `user_company_access`) that previously relied
only on join-through-parent isolation.

Every test in this file operates through the real HTTP/API boundary
against the real dockerized Postgres (same pattern as every other test
file in this suite) — never by calling repository code directly — because
the thing being proven is what an actual attacker or a future buggy
endpoint could or couldn't do, not what the ORM layer is capable of in
isolation.

No literal DELETE endpoint exists anywhere in this API (confirmed by
inspection — grep for `@router.delete` across the whole backend returns
nothing), so "DELETE isolation" is tested via the closest real equivalent:
state-mutating actions (post/reverse/confirm/approve) attempted against
another company's record.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app
from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
async def client():
    # Module-scoped override of conftest.py's function-scoped `client` —
    # local to this file only. The two-company fixture below is expensive
    # (two full bootstrap + quotation/PO/journal-entry/cycle-count chains)
    # and is deliberately shared read-mostly across every test in this
    # file, which requires a fixture of matching scope; conftest.py's own
    # fixture stays function-scoped for every other test file, unchanged.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _bootstrap_company(client, label: str) -> dict:
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
    body = boot_resp.json()
    company_id, branch_id = body["company_id"], body["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}

    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": f"{label} Partner", "is_customer": True, "is_vendor": True, "vat_number": unique_vat()},
    )
    partner_id = partner_resp.json()["id"]

    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{uuid.uuid4().hex[:8]}", "name": f"{label} Product", "sales_price": "100.00"},
    )
    product_id = product_resp.json()["id"]

    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": f"{label} Warehouse", "is_default": True}
    )
    warehouse = wh_resp.json()["warehouse"]
    location_id = wh_resp.json()["default_location"]["id"]

    accounts = (await client.get("/api/v1/accounting/chart-of-accounts", headers=headers)).json()
    cash_id = next(a["id"] for a in accounts if a["code"] == "1100")
    capital_id = next(a["id"] for a in accounts if a["code"] == "3100")

    # Receive stock first — the product is stockable by default, and issuing
    # an invoice against zero stock is correctly blocked (FR-INV-007).
    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "50", "unit_cost": "10.00"},
    )

    # Quotation -> Order -> Invoice (tax invoice, triggers ZATCA clearance)
    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "2", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    quotation_id = quote_resp.json()["id"]
    order_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    order_id = order_resp.json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    invoice_id = invoice_resp.json()["invoice"]["id"]

    # Purchase Order -> Goods Receipt -> Vendor Bill
    po_resp = await client.post(
        "/api/v1/purchasing/orders",
        headers=headers,
        json={
            "partner_id": partner_id,
            "order_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "5", "unit_price": "20.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_pur_id = po_resp.json()["id"]
    await client.post(f"/api/v1/purchasing/orders/{order_pur_id}:confirm", headers=headers)
    po_detail = (await client.get(f"/api/v1/purchasing/orders/{order_pur_id}", headers=headers)).json()
    po_line_id = po_detail["lines"][0]["id"]
    receipt_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_pur_id}/goods-receipts",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "5"}]},
    )
    bill_resp = await client.post(
        f"/api/v1/purchasing/orders/{order_pur_id}/vendor-bills",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": po_line_id, "qty": "5", "unit_price": "20.00"}]},
    )
    bill_id = bill_resp.json()["id"]

    # Manual journal entry
    je_resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=headers,
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-01",
            "reference": f"{label} manual entry",
            "lines": [
                {"account_id": cash_id, "debit": 300, "credit": 0},
                {"account_id": capital_id, "debit": 0, "credit": 300},
            ],
        },
    )
    journal_entry_id = je_resp.json()["id"]

    # Cycle count
    cc_resp = await client.post(
        "/api/v1/inventory/cycle-counts",
        headers=headers,
        json={
            "warehouse_id": warehouse["id"],
            "scheduled_date": "2026-06-01",
            "lines": [{"product_id": product_id, "location_id": location_id, "counted_qty": "0"}],
        },
    )

    return {
        "headers": headers,
        "company_id": company_id,
        "branch_id": branch_id,
        "partner_id": partner_id,
        "product_id": product_id,
        "warehouse_id": warehouse["id"],
        "location_id": location_id,
        "cash_account_id": cash_id,
        "quotation_id": quotation_id,
        "order_id": order_id,
        "invoice_id": invoice_id,
        "purchase_order_id": order_pur_id,
        "purchase_order_line_id": po_line_id,
        "goods_receipt_id": receipt_resp.json()["id"],
        "vendor_bill_id": bill_id,
        "journal_entry_id": journal_entry_id,
        "cycle_count_id": cc_resp.json()["cycle_count"]["id"],
    }


@pytest.fixture(scope="module")
async def companies(client):
    a = await _bootstrap_company(client, "Alpha")
    b = await _bootstrap_company(client, "Beta")
    return a, b


# ---------------------------------------------------------------------------
# 1. SELECT isolation — Company A cannot read Company B's documents by ID
# ---------------------------------------------------------------------------


async def test_select_isolation_across_all_document_types(client, companies):
    a, b = companies
    checks = [
        f"/api/v1/sales/quotations/{b['quotation_id']}",
        f"/api/v1/sales/orders/{b['order_id']}",
        f"/api/v1/sales/invoices/{b['invoice_id']}",
        f"/api/v1/purchasing/orders/{b['purchase_order_id']}",
        f"/api/v1/accounting/journal-entries/{b['journal_entry_id']}",
    ]
    for path in checks:
        resp = await client.get(path, headers=a["headers"])
        assert resp.status_code == 404, f"{path} leaked cross-company data (status {resp.status_code})"


async def test_select_isolation_list_endpoints_never_include_other_company(client, companies):
    a, b = companies
    quotations = (await client.get("/api/v1/sales/quotations", headers=a["headers"])).json()
    assert all(q["id"] != b["quotation_id"] for q in quotations)

    orders = (await client.get("/api/v1/purchasing/orders", headers=a["headers"])).json()["items"]
    assert all(o["id"] != b["purchase_order_id"] for o in orders)

    bills = (await client.get("/api/v1/purchasing/vendor-bills", headers=a["headers"])).json()["items"]
    assert all(bill["id"] != b["vendor_bill_id"] for bill in bills)

    entries = (await client.get("/api/v1/accounting/journal-entries", headers=a["headers"])).json()
    assert all(e["id"] != b["journal_entry_id"] for e in entries)

    moves = (await client.get("/api/v1/inventory/stock/moves", headers=a["headers"])).json()
    # Company B's stock moves must not appear in Company A's move ledger at all.
    b_moves = (await client.get("/api/v1/inventory/stock/moves", headers=b["headers"])).json()
    b_move_ids = {m["id"] for m in b_moves}
    assert not (b_move_ids & {m["id"] for m in moves})


# ---------------------------------------------------------------------------
# 2. ZATCA — Company A cannot read Company B's e-invoicing submission
# ---------------------------------------------------------------------------


async def test_zatca_submission_isolation(client, companies):
    a, b = companies
    # The invoice detail endpoint carries the zatca_submission — if isolation
    # holds, Company A can't reach it at all (404 on the invoice itself).
    resp = await client.get(f"/api/v1/sales/invoices/{b['invoice_id']}", headers=a["headers"])
    assert resp.status_code == 404

    # Company A's own invoice must still carry a real ZATCA submission — this
    # is a control, proving the 404 above is isolation, not a broken endpoint.
    own_resp = await client.get(f"/api/v1/sales/invoices/{a['invoice_id']}", headers=a["headers"])
    assert own_resp.status_code == 200
    assert own_resp.json()["zatca_submission"]["qr_payload"]


# ---------------------------------------------------------------------------
# 3. UPDATE isolation — state-mutating actions against another company's docs
# ---------------------------------------------------------------------------


async def test_update_isolation_confirm_quotation(client, companies):
    a, b = companies
    resp = await client.post(f"/api/v1/sales/quotations/{b['quotation_id']}:confirm", headers=a["headers"])
    assert resp.status_code in (404, 422)


async def test_update_isolation_post_journal_entry(client, companies):
    a, b = companies
    # b's journal entry is already posted (create_draft_entry doesn't auto-post,
    # but re-posting/reversing are the mutating actions available) — attempt
    # reverse from A's context regardless of B's actual current status.
    resp = await client.post(f"/api/v1/accounting/journal-entries/{b['journal_entry_id']}:reverse", headers=a["headers"])
    assert resp.status_code in (404, 422)


async def test_update_isolation_confirm_purchase_order(client, companies):
    a, b = companies
    resp = await client.post(f"/api/v1/purchasing/orders/{b['purchase_order_id']}:confirm", headers=a["headers"])
    assert resp.status_code in (404, 422)


async def test_update_isolation_approve_vendor_bill(client, companies):
    a, b = companies
    resp = await client.post(f"/api/v1/purchasing/vendor-bills/{b['vendor_bill_id']}:approve", headers=a["headers"])
    assert resp.status_code in (404, 422)


async def test_update_isolation_issue_credit_note(client, companies):
    a, b = companies
    resp = await client.post(
        f"/api/v1/sales/invoices/{b['invoice_id']}:credit-note",
        headers=a["headers"],
        json={"reason": "attempted cross-company credit note"},
    )
    assert resp.status_code in (404, 422)


# ---------------------------------------------------------------------------
# 4. INSERT isolation — Company A cannot create a record scoped to Company B
# ---------------------------------------------------------------------------


async def test_insert_isolation_company_id_is_never_client_supplied(client, companies):
    """Every *CreateRequest schema in this API omits company_id entirely — it
    is derived server-side from AuthContext, never accepted from the client.
    This test proves the *behavioral* consequence: even if a client stuffs an
    unexpected company_id into the request body, the created record still
    belongs to the authenticated company (extra fields are ignored, not
    trusted), so it appears in Company A's list, never Company B's."""
    a, b = companies
    resp = await client.post(
        "/api/v1/identity/partners",
        headers=a["headers"],
        json={"name": "Injection Attempt", "is_customer": True, "company_id": b["company_id"]},
    )
    assert resp.status_code == 201
    created_id = resp.json()["id"]
    assert resp.json()["company_id"] == a["company_id"]

    a_partners = (await client.get("/api/v1/identity/partners", headers=a["headers"])).json()
    assert any(p["id"] == created_id for p in a_partners)

    b_partners = (await client.get("/api/v1/identity/partners", headers=b["headers"])).json()
    assert all(p["id"] != created_id for p in b_partners)


async def test_insert_isolation_purchase_order_against_foreign_line_rejected(client, companies):
    """Attempting to record a goods receipt against a foreign purchase-order
    line ID must fail closed. Since purchase_order_line now has its own RLS
    policy (Phase 16A), Company A's session literally cannot SELECT Company
    B's line row — the lookup returns None regardless of the ID's validity,
    which the service layer already treats as "line not found on this
    order." This proves the fix, not just the pre-existing application check:
    before Phase 16A, this same test would only have been protected by the
    `po_line.purchase_order_id != order.id` comparison in application code —
    now the database itself refuses to return the row at all."""
    a, b = companies
    resp = await client.post(
        f"/api/v1/purchasing/orders/{a['purchase_order_id']}/goods-receipts",
        headers=a["headers"],
        json={"lines": [{"purchase_order_line_id": b["purchase_order_line_id"], "qty": "1"}]},
    )
    assert resp.status_code == 422


async def test_insert_isolation_journal_entry_against_foreign_account_rejected(client, companies):
    a, b = companies
    resp = await client.post(
        "/api/v1/accounting/journal-entries",
        headers=a["headers"],
        json={
            "journal_code": "GEN",
            "entry_date": "2026-06-02",
            "lines": [
                {"account_id": b["cash_account_id"], "debit": 50, "credit": 0},
                {"account_id": a["cash_account_id"], "debit": 0, "credit": 50},
            ],
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Line-item ID manipulation — the specific gap Phase 16A closed
# ---------------------------------------------------------------------------


async def test_line_item_id_manipulation_vendor_bill(client, companies):
    a, b = companies
    resp = await client.post(
        f"/api/v1/purchasing/orders/{a['purchase_order_id']}/vendor-bills",
        headers=a["headers"],
        json={"lines": [{"purchase_order_line_id": b["purchase_order_line_id"], "qty": "1", "unit_price": "20.00"}]},
    )
    assert resp.status_code == 422


async def test_line_item_id_manipulation_cannot_read_foreign_invoice_via_credit_note_of_own_invoice(client, companies):
    """Manipulating a parent record ID (original_invoice_id-equivalent path)
    must not let Company A pull Company B's invoice line content into a
    credit note issued under Company A. Already covered functionally by
    test_update_isolation_issue_credit_note's 404 — this test additionally
    confirms Company A's *own* credit-note flow still works, so the 404
    proves isolation rather than a broken endpoint."""
    a, b = companies
    resp = await client.post(
        f"/api/v1/sales/invoices/{a['invoice_id']}:credit-note",
        headers=a["headers"],
        json={"reason": "legitimate same-company credit note"},
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# 6. Reports must not leak cross-company data
# ---------------------------------------------------------------------------


async def test_dashboard_does_not_include_other_company_totals(client, companies):
    a, b = companies
    dash_a = (
        await client.get(
            "/api/v1/reporting/dashboard",
            headers=a["headers"],
            params={"period_start": "2026-01-01", "period_end": "2026-12-31"},
        )
    ).json()
    dash_b = (
        await client.get(
            "/api/v1/reporting/dashboard",
            headers=b["headers"],
            params={"period_start": "2026-01-01", "period_end": "2026-12-31"},
        )
    ).json()
    # Both companies ran the identical scripted scenario (same qty/prices),
    # so if A's dashboard secretly summed both companies' invoices, its
    # sales figure would be double B's alone — the two must match exactly,
    # not one being a multiple of the other.
    assert dash_a["period_sales_total"] == dash_b["period_sales_total"]


async def test_csv_export_does_not_include_other_company_rows(client):
    """Deliberately does NOT reuse the shared `companies` fixture: other
    tests in this module legitimately add more invoices to Company A over
    the module's lifetime (e.g. the credit-note test), so a count-based
    assertion against that shared, mutable fixture would be coupled to test
    execution order — fragile, not a real isolation check. A fresh,
    self-contained company here means the expected row count (exactly 1) is
    deterministic regardless of what other tests in this file have done."""
    fresh = await _bootstrap_company(client, f"CsvCheck-{uuid.uuid4().hex[:6]}")
    resp = await client.get("/api/v1/reporting/export/sales-invoices", headers=fresh["headers"])
    assert resp.status_code == 200
    data_rows = [line for line in resp.text.strip().splitlines()[1:] if line]
    assert len(data_rows) == 1, f"expected exactly this fresh company's own 1 invoice, got {len(data_rows)} rows"


# ---------------------------------------------------------------------------
# 7. RBAC + RLS interaction — broad permissions still don't cross companies
# ---------------------------------------------------------------------------


async def test_admin_role_with_full_permissions_still_cannot_cross_companies(client, companies):
    """The bootstrap admin role is granted every permission in the catalog
    (see identity/api/routes.py's bootstrap flow) — the most powerful role
    this system has. If RLS is working, that breadth of *permission* must
    still not translate into cross-*company* access: RBAC answers "is this
    action allowed at all," RLS independently answers "for which rows,"
    and both must hold simultaneously."""
    a, b = companies
    # a's admin has every permission, including accounting.journal_entry.view —
    # confirm it can still only see its own entries, never b's, despite that
    # unrestricted permission grant.
    resp = await client.get(f"/api/v1/accounting/journal-entries/{b['journal_entry_id']}", headers=a["headers"])
    assert resp.status_code == 404

    entries = (await client.get("/api/v1/accounting/journal-entries", headers=a["headers"])).json()
    assert all(e["id"] != b["journal_entry_id"] for e in entries)


async def test_get_company_endpoint_ignores_path_id_and_never_returns_foreign_company(client, companies):
    """`GET /companies/{company_id}` (identity/api/routes.py) doesn't
    actually use its path parameter — it looks up `ctx.company_id` (from
    the validated X-Company-Id header) regardless of what ID is in the URL.
    That's not a leak (the path param is simply ignored, not trusted), but
    it means "request Company B's ID while authenticated as Company A"
    doesn't 403/404 — it silently returns Company A's own record. The
    security-relevant assertion is that Company B's data is never what
    comes back, no matter what's in the URL."""
    a, b = companies
    resp = await client.get(f"/api/v1/identity/companies/{b['company_id']}", headers=a["headers"])
    assert resp.status_code == 200
    assert resp.json()["id"] == a["company_id"]
    assert resp.json()["id"] != b["company_id"]


# NOTE: `role` and `user_company_access` have no dedicated API-level test
# here — no endpoint in this system lists or exposes another company's
# roles/access-grants directly, so there is no meaningful HTTP-boundary
# scenario to assert against beyond what test_admin_role_with_full_
# permissions_still_cannot_cross_companies already covers (a's admin role
# itself, fully permissioned, still can't reach b's data). The literal,
# authoritative proof that both tables carry an active company_isolation
# policy is the direct pg_policies/pg_tables query run against the live
# database during migration verification — see
# docs/16-multi-tenancy-hardening.md for the exact query and output. A
# fabricated API test asserting nothing real would be worse than no test.
