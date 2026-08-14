"""P0-A (Phase-One closure): the audit found no password-recovery path
anywhere in the codebase. Real SMTP is swapped for a fake via
`app.dependency_overrides` on `get_mailer` — mirrors
test_quotation_email_delivery.py's pattern exactly.
"""

from tests.conftest import unique_email, unique_vat


async def _bootstrap(client, label: str) -> dict:
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
    return payload


def _override_mailer():
    from src.api.main import app
    from src.modules.identity.api.deps import get_mailer

    sent_calls: list[dict] = []

    async def fake_mailer(*, to, subject, body, attachments=None):
        sent_calls.append({"to": to, "subject": subject, "body": body})

    app.dependency_overrides[get_mailer] = lambda: fake_mailer
    return sent_calls


def _clear_mailer_override():
    from src.api.main import app
    from src.modules.identity.api.deps import get_mailer

    app.dependency_overrides.pop(get_mailer, None)


def _extract_token(email_body: str) -> str:
    # PasswordResetService.request_reset puts the raw token alone in its
    # own paragraph (blank line before and after).
    paragraphs = [p.strip() for p in email_body.split("\n\n") if p.strip()]
    for paragraph in paragraphs:
        if " " not in paragraph and len(paragraph) > 20:
            return paragraph
    raise AssertionError(f"could not find a token paragraph in email body: {email_body!r}")


async def test_request_reset_for_known_email_sends_one_token_email(client):
    env = await _bootstrap(client, f"PwReset-Known-{unique_vat()[:6]}")
    sent = _override_mailer()
    try:
        resp = await client.post(
            "/api/v1/identity/auth/password-reset/request", json={"email": env["admin_email"]}
        )
        assert resp.status_code == 200
        assert len(sent) == 1
        assert sent[0]["to"] == env["admin_email"]
    finally:
        _clear_mailer_override()


async def test_request_reset_for_unknown_email_sends_nothing_but_same_response(client):
    sent = _override_mailer()
    try:
        known_resp = await client.post(
            "/api/v1/identity/auth/password-reset/request", json={"email": unique_email()}
        )
    finally:
        _clear_mailer_override()

    assert known_resp.status_code == 200
    assert len(sent) == 0
    assert known_resp.json()["detail"]


async def test_request_reset_response_body_identical_for_known_and_unknown_email(client):
    """Anti-enumeration: the client must not be able to tell the two cases
    apart from the response alone."""
    env = await _bootstrap(client, f"PwReset-AntiEnum-{unique_vat()[:6]}")
    sent = _override_mailer()
    try:
        known_resp = await client.post(
            "/api/v1/identity/auth/password-reset/request", json={"email": env["admin_email"]}
        )
        unknown_resp = await client.post(
            "/api/v1/identity/auth/password-reset/request", json={"email": unique_email()}
        )
    finally:
        _clear_mailer_override()

    assert known_resp.status_code == unknown_resp.status_code == 200
    assert known_resp.json() == unknown_resp.json()
    assert len(sent) == 1


async def test_confirm_with_valid_token_then_login_with_new_password(client):
    env = await _bootstrap(client, f"PwReset-Confirm-{unique_vat()[:6]}")
    sent = _override_mailer()
    try:
        await client.post("/api/v1/identity/auth/password-reset/request", json={"email": env["admin_email"]})
    finally:
        _clear_mailer_override()
    raw_token = _extract_token(sent[0]["body"])

    new_password = "Sup3r$ecureNew1"
    confirm_resp = await client.post(
        "/api/v1/identity/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": new_password},
    )
    assert confirm_resp.status_code == 200, confirm_resp.text

    old_login = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": env["admin_email"], "password": env["admin_password"]},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": env["admin_email"], "password": new_password},
    )
    assert new_login.status_code == 200
    assert new_login.json()["access_token"]


async def test_confirm_token_is_single_use(client):
    env = await _bootstrap(client, f"PwReset-SingleUse-{unique_vat()[:6]}")
    sent = _override_mailer()
    try:
        await client.post("/api/v1/identity/auth/password-reset/request", json={"email": env["admin_email"]})
    finally:
        _clear_mailer_override()
    raw_token = _extract_token(sent[0]["body"])

    first = await client.post(
        "/api/v1/identity/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "Sup3r$ecureNew1"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/identity/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "AnotherOne$2"},
    )
    assert second.status_code == 401


async def test_confirm_with_garbage_token_rejected(client):
    resp = await client.post(
        "/api/v1/identity/auth/password-reset/confirm",
        json={"token": "not-a-real-token", "new_password": "Sup3r$ecureNew1"},
    )
    assert resp.status_code == 401


async def test_confirm_with_weak_new_password_rejected(client):
    env = await _bootstrap(client, f"PwReset-Weak-{unique_vat()[:6]}")
    sent = _override_mailer()
    try:
        await client.post("/api/v1/identity/auth/password-reset/request", json={"email": env["admin_email"]})
    finally:
        _clear_mailer_override()
    raw_token = _extract_token(sent[0]["body"])

    resp = await client.post(
        "/api/v1/identity/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "weak"},
    )
    assert resp.status_code == 422

    # The token must still be usable afterwards — a rejected weak password
    # must not burn the single-use token.
    good_resp = await client.post(
        "/api/v1/identity/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "Sup3r$ecureNew1"},
    )
    assert good_resp.status_code == 200


async def test_request_reset_does_not_require_login_lookup_side_effects(client):
    """The request endpoint must work with no auth headers at all — same
    unauthenticated shape as /auth/login and /auth/refresh."""
    resp = await client.post(
        "/api/v1/identity/auth/password-reset/request", json={"email": unique_email()}
    )
    assert resp.status_code == 200
