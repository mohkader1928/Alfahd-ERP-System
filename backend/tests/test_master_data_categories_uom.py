"""Phase 17B — Product Category, Unit of Measure, Product, and Partner
master-data endpoints: CRUD, validation, hierarchy rules, and cross-company
RLS isolation, all exercised through the real HTTP API against the real
dockerized Postgres (no mocks), per this repo's established test convention.

Authorization note: every new route is verified to require a bearer token
(a request with no Authorization header must be rejected) — this is the
extent of "permission enforcement" testable at the HTTP layer today, since
no endpoint exists anywhere in the API to create a *restricted* role (the
only role ever created is bootstrap's full-access admin role; role
creation/management is explicitly Phase 17H scope). Testing "a non-admin
user is denied a specific permission" would require fabricating a role via
direct repository/service calls, bypassing the HTTP-only black-box style
every other test file in this repo uses — flagged here rather than faked.
"""

import uuid
from decimal import Decimal

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


def _sku() -> str:
    return f"SKU-{uuid.uuid4().hex[:10]}"


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
    assert boot_resp.status_code == 201, boot_resp.text
    body = boot_resp.json()
    company_id, branch_id = body["company_id"], body["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return {"headers": headers, "company_id": company_id, "branch_id": branch_id}


# ---------------------------------------------------------------------------
# Product Category
# ---------------------------------------------------------------------------


async def test_create_root_category(client):
    company = await _bootstrap_company(client, f"CatRoot-{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Electrical"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Electrical"
    assert body["parent_id"] is None


async def test_create_child_category_and_list_is_flat(client):
    company = await _bootstrap_company(client, f"CatChild-{uuid.uuid4().hex[:6]}")
    root = (
        await client.post(
            "/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Electrical"}
        )
    ).json()
    child = await client.post(
        "/api/v1/identity/product-categories",
        headers=company["headers"],
        json={"name": "Lighting", "parent_id": root["id"]},
    )
    assert child.status_code == 201, child.text
    grandchild = await client.post(
        "/api/v1/identity/product-categories",
        headers=company["headers"],
        json={"name": "LED Panels", "parent_id": child.json()["id"]},
    )
    assert grandchild.status_code == 201, grandchild.text

    listed = await client.get("/api/v1/identity/product-categories", headers=company["headers"])
    assert listed.status_code == 200
    names = {row["name"] for row in listed.json()}
    assert {"Electrical", "Lighting", "LED Panels"} <= names
    # Flat list — client assembles the tree; the API itself does no nesting.
    assert all("children" not in row for row in listed.json())


async def test_update_category_name_and_parent(client):
    company = await _bootstrap_company(client, f"CatUpd-{uuid.uuid4().hex[:6]}")
    root_a = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "A"})
    ).json()
    root_b = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "B"})
    ).json()

    resp = await client.patch(
        f"/api/v1/identity/product-categories/{root_a['id']}",
        headers=company["headers"],
        json={"name": "A-renamed", "parent_id": root_b["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "A-renamed"
    assert resp.json()["parent_id"] == root_b["id"]


async def test_delete_valid_category(client):
    company = await _bootstrap_company(client, f"CatDel-{uuid.uuid4().hex[:6]}")
    cat = (
        await client.post(
            "/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Disposable"}
        )
    ).json()
    resp = await client.delete(f"/api/v1/identity/product-categories/{cat['id']}", headers=company["headers"])
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/identity/product-categories/{cat['id']}", headers=company["headers"])
    assert get_resp.status_code == 404


async def test_reject_invalid_parent_category(client):
    company = await _bootstrap_company(client, f"CatBadParent-{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/identity/product-categories",
        headers=company["headers"],
        json={"name": "Orphan", "parent_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


async def test_reject_self_parent(client):
    company = await _bootstrap_company(client, f"CatSelfParent-{uuid.uuid4().hex[:6]}")
    cat = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Self"})
    ).json()
    resp = await client.patch(
        f"/api/v1/identity/product-categories/{cat['id']}",
        headers=company["headers"],
        json={"name": "Self", "parent_id": cat["id"]},
    )
    assert resp.status_code == 422


async def test_reject_circular_hierarchy(client):
    company = await _bootstrap_company(client, f"CatCircular-{uuid.uuid4().hex[:6]}")
    a = (await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "A"})).json()
    b = (
        await client.post(
            "/api/v1/identity/product-categories", headers=company["headers"], json={"name": "B", "parent_id": a["id"]}
        )
    ).json()
    c = (
        await client.post(
            "/api/v1/identity/product-categories", headers=company["headers"], json={"name": "C", "parent_id": b["id"]}
        )
    ).json()
    # Attempt A.parent = C, which is A's own grandchild — a cycle.
    resp = await client.patch(
        f"/api/v1/identity/product-categories/{a['id']}",
        headers=company["headers"],
        json={"name": "A", "parent_id": c["id"]},
    )
    assert resp.status_code == 422


async def test_reject_duplicate_sibling_category_name(client):
    company = await _bootstrap_company(client, f"CatDup-{uuid.uuid4().hex[:6]}")
    root = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Root"})
    ).json()
    first = await client.post(
        "/api/v1/identity/product-categories",
        headers=company["headers"],
        json={"name": "Switches", "parent_id": root["id"]},
    )
    assert first.status_code == 201
    dup = await client.post(
        "/api/v1/identity/product-categories",
        headers=company["headers"],
        json={"name": "Switches", "parent_id": root["id"]},
    )
    assert dup.status_code == 422
    # Same name is fine under a *different* parent (or at root) — proves
    # the check is scoped to siblings, not global.
    other_root = await client.post(
        "/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Switches"}
    )
    assert other_root.status_code == 201


async def test_delete_blocked_by_child_category(client):
    company = await _bootstrap_company(client, f"CatDelChild-{uuid.uuid4().hex[:6]}")
    parent = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Parent"})
    ).json()
    await client.post(
        "/api/v1/identity/product-categories",
        headers=company["headers"],
        json={"name": "Child", "parent_id": parent["id"]},
    )
    resp = await client.delete(f"/api/v1/identity/product-categories/{parent['id']}", headers=company["headers"])
    assert resp.status_code == 422


async def test_delete_blocked_by_product_reference(client):
    company = await _bootstrap_company(client, f"CatDelProd-{uuid.uuid4().hex[:6]}")
    cat = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Cables"})
    ).json()
    await client.post(
        "/api/v1/identity/products",
        headers=company["headers"],
        json={"sku": _sku(), "name": "Cable 2.5mm", "category_id": cat["id"]},
    )
    resp = await client.delete(f"/api/v1/identity/product-categories/{cat['id']}", headers=company["headers"])
    assert resp.status_code == 422


async def test_category_cross_company_isolation(client):
    company_a = await _bootstrap_company(client, f"CatIsoA-{uuid.uuid4().hex[:6]}")
    company_b = await _bootstrap_company(client, f"CatIsoB-{uuid.uuid4().hex[:6]}")

    cat_a = (
        await client.post(
            "/api/v1/identity/product-categories", headers=company_a["headers"], json={"name": "A-only"}
        )
    ).json()

    # B cannot see A's category via list...
    listed_b = await client.get("/api/v1/identity/product-categories", headers=company_b["headers"])
    assert all(row["id"] != cat_a["id"] for row in listed_b.json())

    # ...nor via direct get...
    get_b = await client.get(f"/api/v1/identity/product-categories/{cat_a['id']}", headers=company_b["headers"])
    assert get_b.status_code == 404

    # ...nor use it as a parent for its own category (cross-company FK reject)...
    cross_parent = await client.post(
        "/api/v1/identity/product-categories",
        headers=company_b["headers"],
        json={"name": "B-child", "parent_id": cat_a["id"]},
    )
    assert cross_parent.status_code == 422

    # ...nor modify it.
    cross_update = await client.patch(
        f"/api/v1/identity/product-categories/{cat_a['id']}",
        headers=company_b["headers"],
        json={"name": "Hijacked"},
    )
    assert cross_update.status_code == 404


async def test_product_category_endpoints_require_auth(client):
    resp = await client.get("/api/v1/identity/product-categories")
    assert resp.status_code == 401
    resp = await client.post("/api/v1/identity/product-categories", json={"name": "X"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Unit of Measure
# ---------------------------------------------------------------------------


async def test_create_and_list_uom(client):
    company = await _bootstrap_company(client, f"UomCreate-{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/identity/uom", headers=company["headers"], json={"name": "Piece", "name_ar": "قطعة", "code": "PCS"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["active"] is True

    listed = await client.get("/api/v1/identity/uom", headers=company["headers"])
    assert listed.status_code == 200
    assert any(row["code"] == "PCS" for row in listed.json())


async def test_get_uom_by_id(client):
    company = await _bootstrap_company(client, f"UomGet-{uuid.uuid4().hex[:6]}")
    created = (
        await client.post(
            "/api/v1/identity/uom", headers=company["headers"], json={"name": "Box", "code": "BOX"}
        )
    ).json()
    resp = await client.get(f"/api/v1/identity/uom/{created['id']}", headers=company["headers"])
    assert resp.status_code == 200
    assert resp.json()["code"] == "BOX"


async def test_update_uom(client):
    company = await _bootstrap_company(client, f"UomUpd-{uuid.uuid4().hex[:6]}")
    created = (
        await client.post(
            "/api/v1/identity/uom", headers=company["headers"], json={"name": "Meter", "code": "M"}
        )
    ).json()
    resp = await client.patch(
        f"/api/v1/identity/uom/{created['id']}",
        headers=company["headers"],
        json={"name": "Metre", "name_ar": "متر", "code": "M", "active": True},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Metre"
    assert resp.json()["name_ar"] == "متر"


async def test_deactivate_uom_does_not_break_existing_product_reference(client):
    company = await _bootstrap_company(client, f"UomDeactivate-{uuid.uuid4().hex[:6]}")
    uom = (
        await client.post(
            "/api/v1/identity/uom", headers=company["headers"], json={"name": "Roll", "code": "ROLL"}
        )
    ).json()
    product = (
        await client.post(
            "/api/v1/identity/products",
            headers=company["headers"],
            json={"sku": _sku(), "name": "Cable Roll 100m", "uom_id": uom["id"]},
        )
    ).json()

    deactivate = await client.patch(
        f"/api/v1/identity/uom/{uom['id']}",
        headers=company["headers"],
        json={"name": "Roll", "code": "ROLL", "active": False},
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["active"] is False

    # The product's uom_id FK is untouched — no cascade, no null-out.
    refetched = await client.get(f"/api/v1/identity/products/{product['id']}", headers=company["headers"])
    assert refetched.json()["uom_id"] == uom["id"]


async def test_duplicate_uom_code_rejected(client):
    company = await _bootstrap_company(client, f"UomDup-{uuid.uuid4().hex[:6]}")
    first = await client.post(
        "/api/v1/identity/uom", headers=company["headers"], json={"name": "Set", "code": "SET"}
    )
    assert first.status_code == 201
    dup = await client.post(
        "/api/v1/identity/uom", headers=company["headers"], json={"name": "Set (duplicate)", "code": "SET"}
    )
    assert dup.status_code == 422
    # Case-insensitive duplicate check.
    dup_case = await client.post(
        "/api/v1/identity/uom", headers=company["headers"], json={"name": "set lower", "code": "set"}
    )
    assert dup_case.status_code == 422


async def test_uom_cross_company_isolation(client):
    company_a = await _bootstrap_company(client, f"UomIsoA-{uuid.uuid4().hex[:6]}")
    company_b = await _bootstrap_company(client, f"UomIsoB-{uuid.uuid4().hex[:6]}")

    uom_a = (
        await client.post(
            "/api/v1/identity/uom", headers=company_a["headers"], json={"name": "A-only", "code": "AONLY"}
        )
    ).json()

    listed_b = await client.get("/api/v1/identity/uom", headers=company_b["headers"])
    assert all(row["id"] != uom_a["id"] for row in listed_b.json())

    get_b = await client.get(f"/api/v1/identity/uom/{uom_a['id']}", headers=company_b["headers"])
    assert get_b.status_code == 404

    # Company B can reuse the same *code* — uniqueness is per-company, not global.
    same_code_b = await client.post(
        "/api/v1/identity/uom", headers=company_b["headers"], json={"name": "B version", "code": "AONLY"}
    )
    assert same_code_b.status_code == 201


async def test_uom_endpoints_require_auth(client):
    resp = await client.get("/api/v1/identity/uom")
    assert resp.status_code == 401
    resp = await client.post("/api/v1/identity/uom", json={"name": "X", "code": "X"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Product — category/UOM assignment, update, filtering, cross-company reject
# ---------------------------------------------------------------------------


async def test_create_product_with_category_and_uom(client):
    company = await _bootstrap_company(client, f"ProdCreate-{uuid.uuid4().hex[:6]}")
    cat = (
        await client.post(
            "/api/v1/identity/product-categories", headers=company["headers"], json={"name": "LED Panels"}
        )
    ).json()
    uom = (
        await client.post(
            "/api/v1/identity/uom", headers=company["headers"], json={"name": "Piece", "code": "PCS"}
        )
    ).json()

    resp = await client.post(
        "/api/v1/identity/products",
        headers=company["headers"],
        json={
            "sku": _sku(),
            "name": "LED Panel 60x60",
            "category_id": cat["id"],
            "uom_id": uom["id"],
            "cost_price": "80.00",
            "sales_price": "150.00",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["category_id"] == cat["id"]
    assert body["uom_id"] == uom["id"]
    assert Decimal(body["cost_price"]) == Decimal("80.00")


async def test_update_product_category_and_uom(client):
    company = await _bootstrap_company(client, f"ProdUpd-{uuid.uuid4().hex[:6]}")
    cat1 = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Cat1"})
    ).json()
    cat2 = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "Cat2"})
    ).json()
    uom = (
        await client.post("/api/v1/identity/uom", headers=company["headers"], json={"name": "Box", "code": "BOX"})
    ).json()
    product = (
        await client.post(
            "/api/v1/identity/products",
            headers=company["headers"],
            json={"sku": _sku(), "name": "Widget", "category_id": cat1["id"]},
        )
    ).json()

    resp = await client.patch(
        f"/api/v1/identity/products/{product['id']}",
        headers=company["headers"],
        json={
            "sku": product["sku"],
            "name": "Widget v2",
            "category_id": cat2["id"],
            "uom_id": uom["id"],
            "sales_price": "10.00",
            "cost_price": "5.00",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["category_id"] == cat2["id"]
    assert resp.json()["uom_id"] == uom["id"]
    assert resp.json()["name"] == "Widget v2"


async def test_filter_products_by_category(client):
    company = await _bootstrap_company(client, f"ProdFilter-{uuid.uuid4().hex[:6]}")
    cat_a = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "FiltA"})
    ).json()
    cat_b = (
        await client.post("/api/v1/identity/product-categories", headers=company["headers"], json={"name": "FiltB"})
    ).json()
    await client.post(
        "/api/v1/identity/products",
        headers=company["headers"],
        json={"sku": _sku(), "name": "In A", "category_id": cat_a["id"]},
    )
    await client.post(
        "/api/v1/identity/products",
        headers=company["headers"],
        json={"sku": _sku(), "name": "In B", "category_id": cat_b["id"]},
    )

    resp = await client.get(
        "/api/v1/identity/products", headers=company["headers"], params={"category_id": cat_a["id"]}
    )
    assert resp.status_code == 200
    names = {row["name"] for row in resp.json()}
    assert names == {"In A"}


async def test_create_product_cross_company_category_rejected(client):
    company_a = await _bootstrap_company(client, f"ProdCatIsoA-{uuid.uuid4().hex[:6]}")
    company_b = await _bootstrap_company(client, f"ProdCatIsoB-{uuid.uuid4().hex[:6]}")
    cat_a = (
        await client.post(
            "/api/v1/identity/product-categories", headers=company_a["headers"], json={"name": "A-cat"}
        )
    ).json()

    resp = await client.post(
        "/api/v1/identity/products",
        headers=company_b["headers"],
        json={"sku": _sku(), "name": "Cross-company product", "category_id": cat_a["id"]},
    )
    assert resp.status_code == 422


async def test_create_product_cross_company_uom_rejected(client):
    company_a = await _bootstrap_company(client, f"ProdUomIsoA-{uuid.uuid4().hex[:6]}")
    company_b = await _bootstrap_company(client, f"ProdUomIsoB-{uuid.uuid4().hex[:6]}")
    uom_a = (
        await client.post(
            "/api/v1/identity/uom", headers=company_a["headers"], json={"name": "A-uom", "code": "AUOM"}
        )
    ).json()

    resp = await client.post(
        "/api/v1/identity/products",
        headers=company_b["headers"],
        json={"sku": _sku(), "name": "Cross-company product", "uom_id": uom_a["id"]},
    )
    assert resp.status_code == 422


async def test_product_rls_isolation_get_and_list(client):
    company_a = await _bootstrap_company(client, f"ProdRlsA-{uuid.uuid4().hex[:6]}")
    company_b = await _bootstrap_company(client, f"ProdRlsB-{uuid.uuid4().hex[:6]}")
    product_a = (
        await client.post(
            "/api/v1/identity/products",
            headers=company_a["headers"],
            json={"sku": _sku(), "name": "A-only product"},
        )
    ).json()

    get_b = await client.get(f"/api/v1/identity/products/{product_a['id']}", headers=company_b["headers"])
    assert get_b.status_code == 404

    list_b = await client.get("/api/v1/identity/products", headers=company_b["headers"])
    assert all(row["id"] != product_a["id"] for row in list_b.json())


async def test_product_get_and_update_endpoints_require_auth(client):
    resp = await client.get(f"/api/v1/identity/products/{uuid.uuid4()}")
    assert resp.status_code == 401
    resp = await client.patch(f"/api/v1/identity/products/{uuid.uuid4()}", json={"sku": "X", "name": "X"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Partner — customer/vendor, address, update, cross-company isolation
# ---------------------------------------------------------------------------


async def test_create_customer_and_vendor_partners(client):
    company = await _bootstrap_company(client, f"PartnerCV-{uuid.uuid4().hex[:6]}")
    customer = await client.post(
        "/api/v1/identity/partners",
        headers=company["headers"],
        json={"name": "Alfahd Electrical", "is_customer": True},
    )
    assert customer.status_code == 201
    assert customer.json()["is_customer"] is True
    assert customer.json()["is_vendor"] is False

    vendor = await client.post(
        "/api/v1/identity/partners",
        headers=company["headers"],
        json={"name": "Riyadh Cable Supplier", "is_vendor": True},
    )
    assert vendor.status_code == 201
    assert vendor.json()["is_vendor"] is True
    assert vendor.json()["is_customer"] is False


async def test_customer_vendor_filters_stay_separate(client):
    company = await _bootstrap_company(client, f"PartnerSep-{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/identity/partners", headers=company["headers"], json={"name": "Cust Only", "is_customer": True}
    )
    await client.post(
        "/api/v1/identity/partners", headers=company["headers"], json={"name": "Vend Only", "is_vendor": True}
    )

    customers = await client.get(
        "/api/v1/identity/partners", headers=company["headers"], params={"customers_only": "true"}
    )
    vendors = await client.get(
        "/api/v1/identity/partners", headers=company["headers"], params={"vendors_only": "true"}
    )
    assert {row["name"] for row in customers.json()} == {"Cust Only"}
    assert {row["name"] for row in vendors.json()} == {"Vend Only"}


async def test_update_partner_address(client):
    company = await _bootstrap_company(client, f"PartnerAddr-{uuid.uuid4().hex[:6]}")
    partner = (
        await client.post(
            "/api/v1/identity/partners",
            headers=company["headers"],
            json={"name": "Needs Address", "is_customer": True},
        )
    ).json()
    assert partner["address"] is None

    resp = await client.patch(
        f"/api/v1/identity/partners/{partner['id']}",
        headers=company["headers"],
        json={
            "name": "Needs Address",
            "is_customer": True,
            "address": {
                "street": "King Fahd Rd",
                "city": "Riyadh",
                "region": "Riyadh Province",
                "postal_code": "12345",
                "country_code": "SA",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["address"]["city"] == "Riyadh"
    assert resp.json()["address"]["country_code"] == "SA"


async def test_get_partner_master_data(client):
    company = await _bootstrap_company(client, f"PartnerGet-{uuid.uuid4().hex[:6]}")
    partner = (
        await client.post(
            "/api/v1/identity/partners",
            headers=company["headers"],
            json={"name": "Lookup Me", "is_customer": True, "vat_number": unique_vat()},
        )
    ).json()
    resp = await client.get(f"/api/v1/identity/partners/{partner['id']}", headers=company["headers"])
    assert resp.status_code == 200
    assert resp.json()["name"] == "Lookup Me"
    assert resp.json()["is_active"] is True


async def test_update_partner_may_clear_all_role_flags(client):
    """Unified Address Book bundle: a Partner with no Customer/Vendor/
    Employee role is a legitimate state (a plain Address Book entry, or a
    Contact Person under a company) — the old "must be customer or vendor"
    rule was removed, since Employee and Contact are now first-class roles
    too and neither requires Customer/Vendor to be set."""
    company = await _bootstrap_company(client, f"PartnerReq-{uuid.uuid4().hex[:6]}")
    partner = (
        await client.post(
            "/api/v1/identity/partners", headers=company["headers"], json={"name": "Valid", "is_customer": True}
        )
    ).json()
    resp = await client.patch(
        f"/api/v1/identity/partners/{partner['id']}",
        headers=company["headers"],
        json={"name": "Valid", "is_customer": False, "is_vendor": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_customer"] is False
    assert resp.json()["is_vendor"] is False


async def test_partner_cross_company_isolation(client):
    company_a = await _bootstrap_company(client, f"PartnerIsoA-{uuid.uuid4().hex[:6]}")
    company_b = await _bootstrap_company(client, f"PartnerIsoB-{uuid.uuid4().hex[:6]}")
    partner_a = (
        await client.post(
            "/api/v1/identity/partners",
            headers=company_a["headers"],
            json={"name": "A-only partner", "is_customer": True},
        )
    ).json()

    get_b = await client.get(f"/api/v1/identity/partners/{partner_a['id']}", headers=company_b["headers"])
    assert get_b.status_code == 404

    update_b = await client.patch(
        f"/api/v1/identity/partners/{partner_a['id']}",
        headers=company_b["headers"],
        json={"name": "Hijacked", "is_customer": True},
    )
    assert update_b.status_code == 404

    list_b = await client.get("/api/v1/identity/partners", headers=company_b["headers"])
    assert all(row["id"] != partner_a["id"] for row in list_b.json())


async def test_partner_endpoints_require_auth(client):
    resp = await client.get(f"/api/v1/identity/partners/{uuid.uuid4()}")
    assert resp.status_code == 401
    resp = await client.patch(f"/api/v1/identity/partners/{uuid.uuid4()}", json={"name": "X"})
    assert resp.status_code == 401
