"""Owner directive: every master-data business code (Product SKU, Partner
code — Customer/Vendor/Employee/Contact all share the one Partner table)
must be system-assigned and guaranteed unique, never left to the user to
type. Mirrors the pattern FixedAsset.asset_code already used (see
test_fixed_assets.py::test_create_fixed_asset_posts_acquisition_entry)."""

from tests.conftest import unique_email, unique_vat


async def _bootstrap_and_login(client, label="AutoCode"):
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
    resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    company_id = resp.json()["company_id"]
    branch_id = resp.json()["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}
    return company_id, headers


async def test_product_sku_is_system_assigned_and_sequential(client):
    _, headers = await _bootstrap_and_login(client, "AutoCode_Product")

    resp1 = await client.post("/api/v1/identity/products", headers=headers, json={"name": "Widget A"})
    assert resp1.status_code == 201, resp1.text
    assert resp1.json()["sku"] == "PROD-000001"

    resp2 = await client.post("/api/v1/identity/products", headers=headers, json={"name": "Widget B"})
    assert resp2.json()["sku"] == "PROD-000002"


async def test_product_sku_client_supplied_value_is_ignored(client):
    """Even if a caller sends a `sku`, ProductCreateRequest no longer has
    that field — FastAPI/Pydantic silently drops unknown keys, and the
    server-assigned SKU is used regardless."""
    _, headers = await _bootstrap_and_login(client, "AutoCode_ProductIgnoreSku")

    resp = await client.post(
        "/api/v1/identity/products", headers=headers, json={"name": "Widget", "sku": "HACKED-SKU"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["sku"] == "PROD-000001"


async def test_product_sku_sequence_is_isolated_per_company(client):
    _, headers_a = await _bootstrap_and_login(client, "AutoCode_ProductTenantA")
    _, headers_b = await _bootstrap_and_login(client, "AutoCode_ProductTenantB")

    resp_a = await client.post("/api/v1/identity/products", headers=headers_a, json={"name": "A-only"})
    resp_b = await client.post("/api/v1/identity/products", headers=headers_b, json={"name": "B-only"})
    assert resp_a.json()["sku"] == "PROD-000001"
    assert resp_b.json()["sku"] == "PROD-000001"  # separate company -> own sequence


async def test_partner_code_is_system_assigned_and_sequential(client):
    _, headers = await _bootstrap_and_login(client, "AutoCode_Partner")

    resp1 = await client.post("/api/v1/identity/partners", headers=headers, json={"name": "ACME Corp"})
    assert resp1.status_code == 201, resp1.text
    assert resp1.json()["partner_code"] == "PTR-000001"

    resp2 = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Beta Vendor", "is_vendor": True}
    )
    assert resp2.json()["partner_code"] == "PTR-000002"

    # Listing surfaces the same codes.
    listing = await client.get("/api/v1/identity/partners", headers=headers)
    codes = {p["partner_code"] for p in listing.json()}
    assert codes == {"PTR-000001", "PTR-000002"}


async def test_partner_code_sequence_is_isolated_per_company(client):
    _, headers_a = await _bootstrap_and_login(client, "AutoCode_PartnerTenantA")
    _, headers_b = await _bootstrap_and_login(client, "AutoCode_PartnerTenantB")

    resp_a = await client.post("/api/v1/identity/partners", headers=headers_a, json={"name": "A Partner"})
    resp_b = await client.post("/api/v1/identity/partners", headers=headers_b, json={"name": "B Partner"})
    assert resp_a.json()["partner_code"] == "PTR-000001"
    assert resp_b.json()["partner_code"] == "PTR-000001"


async def test_partner_create_request_has_no_code_field(client):
    """A caller cannot influence the code even if they try — there is no
    `partner_code` key on PartnerCreateRequest at all."""
    _, headers = await _bootstrap_and_login(client, "AutoCode_PartnerIgnoreCode")

    resp = await client.post(
        "/api/v1/identity/partners", headers=headers, json={"name": "Gamma LLC", "partner_code": "HACKED-CODE"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["partner_code"] == "PTR-000001"
