"""UI/UX Evolution milestone — Entity Media Foundation.

Exercises the shared image upload/delete path for Company logo, Partner
(customer/vendor) image, and Product image through the real HTTP layer —
same validation logic (backend/src/shared/media/storage.py) reused by all
three, so these tests double as coverage for that shared module.
"""

from tests.conftest import unique_email, unique_vat

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Media Test Holding",
        "company_legal_name": "Media Test Co.",
        "company_legal_name_ar": "شركة اختبار الوسائط",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Media Test Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    company_id = resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return headers, company_id


async def test_upload_and_delete_company_logo(client):
    headers, company_id = await _bootstrap_and_login(client)

    upload_resp = await client.post(
        f"/api/v1/identity/companies/{company_id}/logo",
        headers=headers,
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert upload_resp.status_code == 200
    logo_path = upload_resp.json()["logo_path"]
    assert logo_path is not None
    assert logo_path.startswith("company/")

    # The stored path is real and actually served back out.
    media_resp = await client.get(f"/media/{logo_path}")
    assert media_resp.status_code == 200
    assert media_resp.content == PNG_BYTES

    get_resp = await client.get(f"/api/v1/identity/companies/{company_id}", headers=headers)
    assert get_resp.json()["logo_path"] == logo_path

    delete_resp = await client.delete(f"/api/v1/identity/companies/{company_id}/logo", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["logo_path"] is None

    # The old file is actually removed from disk, not just unlinked in the DB.
    media_resp_after = await client.get(f"/media/{logo_path}")
    assert media_resp_after.status_code == 404


async def test_replacing_company_logo_removes_the_old_file(client):
    headers, company_id = await _bootstrap_and_login(client)

    first = await client.post(
        f"/api/v1/identity/companies/{company_id}/logo",
        headers=headers,
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    first_path = first.json()["logo_path"]

    second = await client.post(
        f"/api/v1/identity/companies/{company_id}/logo",
        headers=headers,
        files={"file": ("logo2.png", PNG_BYTES, "image/png")},
    )
    second_path = second.json()["logo_path"]
    assert second_path != first_path

    stale = await client.get(f"/media/{first_path}")
    assert stale.status_code == 404
    fresh = await client.get(f"/media/{second_path}")
    assert fresh.status_code == 200


async def test_upload_company_logo_rejects_invalid_content_type(client):
    headers, company_id = await _bootstrap_and_login(client)

    resp = await client.post(
        f"/api/v1/identity/companies/{company_id}/logo",
        headers=headers,
        files={"file": ("logo.txt", b"not an image", "text/plain")},
    )
    assert resp.status_code == 422
    assert "Unsupported image type" in resp.json()["detail"]


async def test_upload_company_logo_rejects_oversized_file(client):
    headers, company_id = await _bootstrap_and_login(client)

    oversized = b"\x00" * (2 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/api/v1/identity/companies/{company_id}/logo",
        headers=headers,
        files={"file": ("logo.png", oversized, "image/png")},
    )
    assert resp.status_code == 422
    assert "exceeds" in resp.json()["detail"]


async def test_upload_company_logo_requires_permission(client):
    """A user with zero role assignment has zero permissions in that
    company — the same real-permission-data pattern used in
    test_identity_m0_smoke.py, not a mocked check."""
    headers, company_id = await _bootstrap_and_login(client)

    no_role_email = unique_email()
    create_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={
            "email": no_role_email,
            "full_name": "No Role User",
            "password": "Str0ng!Passw0rd",
            "company_id": company_id,
        },
    )
    assert create_resp.status_code == 201

    no_role_login = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": no_role_email, "password": "Str0ng!Passw0rd"},
    )
    no_role_token = no_role_login.json()["access_token"]
    no_role_headers = {"Authorization": f"Bearer {no_role_token}", "X-Company-Id": company_id}

    resp = await client.post(
        f"/api/v1/identity/companies/{company_id}/logo",
        headers=no_role_headers,
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 403


async def test_upload_and_delete_partner_image(client):
    headers, company_id = await _bootstrap_and_login(client)

    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "Media Test Customer", "is_customer": True},
    )
    partner_id = partner_resp.json()["id"]

    upload_resp = await client.post(
        f"/api/v1/identity/partners/{partner_id}/image",
        headers=headers,
        files={"file": ("avatar.webp", PNG_BYTES, "image/webp")},
    )
    assert upload_resp.status_code == 200
    image_path = upload_resp.json()["image_path"]
    assert image_path.startswith("partner/")

    media_resp = await client.get(f"/media/{image_path}")
    assert media_resp.status_code == 200
    # Owner-reported bug: this exact scenario (webp upload + fetch) already
    # passed here on status code alone while the response's actual
    # Content-Type silently came back as application/octet-stream instead
    # of image/webp — status 200 was never enough to catch it. Browsers
    # refuse to render an <img> whose Content-Type isn't image/*, so the
    # upload "succeeded" (success toast, correct DB row, correct bytes on
    # disk) while the photo simply never appeared. See main.py's
    # mimetypes.add_type("image/webp", ".webp") registration.
    assert media_resp.headers["content-type"] == "image/webp"

    delete_resp = await client.delete(f"/api/v1/identity/partners/{partner_id}/image", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["image_path"] is None


async def test_upload_and_delete_product_image(client):
    headers, company_id = await _bootstrap_and_login(client)

    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": "MEDIA-TEST-001", "name": "Media Test Product"},
    )
    product_id = product_resp.json()["id"]

    upload_resp = await client.post(
        f"/api/v1/identity/products/{product_id}/image",
        headers=headers,
        files={"file": ("product.jpg", PNG_BYTES, "image/jpeg")},
    )
    assert upload_resp.status_code == 200
    image_path = upload_resp.json()["image_path"]
    assert image_path.startswith("product/")

    delete_resp = await client.delete(f"/api/v1/identity/products/{product_id}/image", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["image_path"] is None


async def test_partner_image_upload_rejects_cross_company_partner(client):
    """A partner belonging to a different company must 404, not leak
    existence or allow a cross-tenant write — same boundary get_partner()/
    update_partner() already enforce."""
    headers_a, _ = await _bootstrap_and_login(client)
    headers_b, _ = await _bootstrap_and_login(client)

    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers_a,
        json={"name": "Company A Only Partner", "is_customer": True},
    )
    partner_a_id = partner_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/identity/partners/{partner_a_id}/image",
        headers=headers_b,
        files={"file": ("avatar.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 404
