"""Integration smoke test for Document Delivery — Sales Invoice PDF +
Send by Email (Product Owner audit: no PDF existed for the actual invoice
document, and no email-sending mechanism existed anywhere in the system).

The real SMTP send is swapped for a fake via `app.dependency_overrides` on
`get_mailer` — this is a deliberate integration-test boundary: everything
up to and including composing the email (permission check, PDF generation,
recipient resolution, DB update) is exercised for real; only the actual
network call to an SMTP server is faked, the same way this codebase's
ZATCA sandbox gateway avoids a real external call rather than trying to
mock it away.
"""

from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_and_login(client):
    payload = {
        "tenant_legal_name": "Email Test Holding",
        "company_legal_name": "Email Test Trading Co.",
        "company_legal_name_ar": "Email Test Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Email Test Admin",
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


async def _issue_invoice(client, headers, *, partner_email: str | None):
    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "Email Test Customer", "is_customer": True, "email": partner_email},
    )
    partner_id = partner_resp.json()["id"]
    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"EMAIL-{unique_vat()[:8]}", "name": "Email Test Product", "sales_price": "100.00"},
    )
    product_id = product_resp.json()["id"]
    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-08-01",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    order_id = (await client.post(f"/api/v1/sales/quotations/{quote_resp.json()['id']}:confirm", headers=headers)).json()["id"]
    invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    assert invoice_resp.status_code == 201
    return invoice_resp.json()["invoice"]


async def test_invoice_pdf_download_returns_a_real_pdf(client):
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_invoice(client, headers, partner_email=None)

    resp = await client.get(f"/api/v1/sales/invoices/{invoice['id']}/pdf", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


async def test_send_email_defaults_to_partner_email_and_records_it(client):
    from src.api.main import app
    from src.modules.sales.api.deps import get_mailer

    sent_calls = []

    async def fake_mailer(*, to, subject, body, attachments=None):
        sent_calls.append({"to": to, "subject": subject, "body": body, "attachments": attachments})

    app.dependency_overrides[get_mailer] = lambda: fake_mailer
    try:
        _, headers = await _bootstrap_and_login(client)
        invoice = await _issue_invoice(client, headers, partner_email="customer@example.com")

        resp = await client.post(f"/api/v1/sales/invoices/{invoice['id']}:send-email", headers=headers, json={})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["last_emailed_to"] == "customer@example.com"
        assert body["last_emailed_at"] is not None

        assert len(sent_calls) == 1
        assert sent_calls[0]["to"] == "customer@example.com"
        assert invoice["number"] in sent_calls[0]["subject"]
        assert len(sent_calls[0]["attachments"]) == 1
        assert sent_calls[0]["attachments"][0].content[:4] == b"%PDF"
        assert sent_calls[0]["attachments"][0].filename == f"{invoice['number']}.pdf"
    finally:
        app.dependency_overrides.pop(get_mailer, None)


async def test_send_email_explicit_recipient_overrides_partner_email(client):
    from src.api.main import app
    from src.modules.sales.api.deps import get_mailer

    sent_calls = []

    async def fake_mailer(*, to, subject, body, attachments=None):
        sent_calls.append(to)

    app.dependency_overrides[get_mailer] = lambda: fake_mailer
    try:
        _, headers = await _bootstrap_and_login(client)
        invoice = await _issue_invoice(client, headers, partner_email="on-file@example.com")

        resp = await client.post(
            f"/api/v1/sales/invoices/{invoice['id']}:send-email",
            headers=headers,
            json={"to_email": "one-off@example.com"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["last_emailed_to"] == "one-off@example.com"
        assert sent_calls == ["one-off@example.com"]
    finally:
        app.dependency_overrides.pop(get_mailer, None)


async def test_send_email_without_recipient_or_partner_email_is_rejected(client):
    from src.api.main import app
    from src.modules.sales.api.deps import get_mailer

    async def fake_mailer(**kwargs):
        raise AssertionError("mailer should never be called when there's no recipient")

    app.dependency_overrides[get_mailer] = lambda: fake_mailer
    try:
        _, headers = await _bootstrap_and_login(client)
        invoice = await _issue_invoice(client, headers, partner_email=None)

        resp = await client.post(f"/api/v1/sales/invoices/{invoice['id']}:send-email", headers=headers, json={})
        assert resp.status_code == 422
        assert "email" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_mailer, None)


async def test_send_email_without_permission_is_rejected(client):
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_invoice(client, headers, partner_email="customer@example.com")

    role_resp = await client.post("/api/v1/identity/roles", headers=headers, json={"name": "No Email"})
    role_id = role_resp.json()["id"]
    await client.put(
        f"/api/v1/identity/roles/{role_id}/permissions",
        headers=headers,
        json={"permission_codes": ["sales.invoice.create"]},
    )
    company_id = headers["X-Company-Id"]
    email = unique_email()
    password = "Str0ng!Passw0rd"
    create_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": email, "full_name": "No Email User", "password": password, "company_id": company_id},
    )
    user_id = create_resp.json()["id"]
    await client.post(f"/api/v1/identity/users/{user_id}/roles", headers=headers, json={"role_id": role_id})
    login_resp = await client.post("/api/v1/identity/auth/login", json={"email": email, "password": password})
    no_perm_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}", "X-Company-Id": company_id}

    resp = await client.post(f"/api/v1/sales/invoices/{invoice['id']}:send-email", headers=no_perm_headers, json={})
    assert resp.status_code == 403


async def test_send_email_without_smtp_configured_returns_actionable_422(client):
    """No dependency override here — exercises the REAL `send_email`, whose
    settings.smtp_host is unset in this test environment (no SMTP server
    exists in this stack), proving the failure is a clear, catchable error
    rather than an unhandled exception or a silent no-op."""
    _, headers = await _bootstrap_and_login(client)
    invoice = await _issue_invoice(client, headers, partner_email="customer@example.com")

    resp = await client.post(f"/api/v1/sales/invoices/{invoice['id']}:send-email", headers=headers, json={})
    assert resp.status_code == 422
    assert "smtp" in resp.json()["detail"].lower() or "configured" in resp.json()["detail"].lower()
