"""Integration smoke test for Attachments (Professional Workspace Layer).

Every reference ERP lets a user attach an arbitrary file to any business
document; this system had zero such mechanism outside product/partner/
company logos. Exercises upload/list/download/delete end to end through
the real HTTP layer, against the real database (including RLS).
"""

import uuid

from tests.conftest import unique_email, unique_vat


async def _bootstrap(client):
    payload = {
        "tenant_legal_name": "Attachment Test Holding",
        "company_legal_name": "Attachment Test Trading Co.",
        "company_legal_name_ar": "Attachment Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Attachment Test Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201
    company_id = boot_resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return company_id, headers


async def test_upload_and_list_attachment(client):
    _, headers = await _bootstrap(client)
    entity_id = str(uuid.uuid4())

    upload_resp = await client.post(
        "/api/v1/attachments",
        headers=headers,
        params={"entity_type": "sales_invoice", "entity_id": entity_id},
        files={"file": ("invoice_scan.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    body = upload_resp.json()
    assert body["original_filename"] == "invoice_scan.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["file_size"] == len(b"%PDF-1.4 fake pdf content")
    assert body["entity_type"] == "sales_invoice"
    assert body["entity_id"] == entity_id
    assert body["uploaded_by_name"] == "Attachment Test Admin"

    list_resp = await client.get(
        "/api/v1/attachments", headers=headers, params={"entity_type": "sales_invoice", "entity_id": entity_id}
    )
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["id"] == body["id"]


async def test_download_attachment_returns_real_bytes(client):
    _, headers = await _bootstrap(client)
    entity_id = str(uuid.uuid4())
    content = b"%PDF-1.4 the real bytes of this file"

    upload_resp = await client.post(
        "/api/v1/attachments",
        headers=headers,
        params={"entity_type": "purchase_order", "entity_id": entity_id},
        files={"file": ("po.pdf", content, "application/pdf")},
    )
    attachment_id = upload_resp.json()["id"]

    download_resp = await client.get(f"/api/v1/attachments/{attachment_id}/download", headers=headers)
    assert download_resp.status_code == 200
    assert download_resp.content == content
    assert "po.pdf" in download_resp.headers["content-disposition"]


async def test_delete_attachment_removes_it(client):
    _, headers = await _bootstrap(client)
    entity_id = str(uuid.uuid4())

    upload_resp = await client.post(
        "/api/v1/attachments",
        headers=headers,
        params={"entity_type": "vendor_bill", "entity_id": entity_id},
        files={"file": ("bill.pdf", b"%PDF-1.4 x", "application/pdf")},
    )
    attachment_id = upload_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/attachments/{attachment_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp = await client.get(
        "/api/v1/attachments", headers=headers, params={"entity_type": "vendor_bill", "entity_id": entity_id}
    )
    assert list_resp.json() == []

    download_resp = await client.get(f"/api/v1/attachments/{attachment_id}/download", headers=headers)
    assert download_resp.status_code == 404


async def test_attachment_rejects_unsupported_content_type(client):
    _, headers = await _bootstrap(client)
    entity_id = str(uuid.uuid4())

    upload_resp = await client.post(
        "/api/v1/attachments",
        headers=headers,
        params={"entity_type": "sales_invoice", "entity_id": entity_id},
        files={"file": ("malware.exe", b"MZ fake exe", "application/x-msdownload")},
    )
    assert upload_resp.status_code == 422


async def test_attachments_isolated_across_companies(client):
    _, headers_a = await _bootstrap(client)
    entity_id = str(uuid.uuid4())
    upload_resp = await client.post(
        "/api/v1/attachments",
        headers=headers_a,
        params={"entity_type": "sales_invoice", "entity_id": entity_id},
        files={"file": ("secret.pdf", b"%PDF-1.4 secret", "application/pdf")},
    )
    attachment_id = upload_resp.json()["id"]

    _, headers_b = await _bootstrap(client)
    list_resp = await client.get(
        "/api/v1/attachments", headers=headers_b, params={"entity_type": "sales_invoice", "entity_id": entity_id}
    )
    assert list_resp.json() == []

    download_resp = await client.get(f"/api/v1/attachments/{attachment_id}/download", headers=headers_b)
    assert download_resp.status_code == 404


async def test_attachments_require_permission(client):
    resp = await client.get(
        "/api/v1/attachments", params={"entity_type": "sales_invoice", "entity_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 401
