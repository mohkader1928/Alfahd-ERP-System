"""P0-B (Phase-One closure): the audit found no brute-force protection on
the login/2FA guess surface at all. AuthenticationService.MAX_FAILED_LOGIN_ATTEMPTS
(5) / LOCKOUT_DURATION_MINUTES (15) — see services.py for the design
rationale (auto-expiring, never permanent; P0-A's password reset also
clears it as the recovery path).
"""

from src.modules.identity.application.services import AuthenticationService
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


async def _wrong_password_attempt(client, email: str) -> int:
    resp = await client.post(
        "/api/v1/identity/auth/login", json={"email": email, "password": "definitely-wrong-1A!"}
    )
    return resp.status_code


async def test_account_locks_after_max_failed_attempts(client):
    env = await _bootstrap(client, f"Lockout-Basic-{unique_vat()[:6]}")

    for _ in range(AuthenticationService.MAX_FAILED_LOGIN_ATTEMPTS):
        status = await _wrong_password_attempt(client, env["admin_email"])
        assert status == 401

    # Even the CORRECT password is now rejected — the account is locked.
    resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": env["admin_email"], "password": env["admin_password"]},
    )
    assert resp.status_code == 401
    assert "locked" in resp.json()["detail"].lower()


async def test_lockout_message_is_distinct_from_invalid_credentials(client):
    env = await _bootstrap(client, f"Lockout-Message-{unique_vat()[:6]}")

    wrong_resp = await client.post(
        "/api/v1/identity/auth/login", json={"email": env["admin_email"], "password": "wrong-1A!"}
    )
    assert "locked" not in wrong_resp.json()["detail"].lower()

    for _ in range(AuthenticationService.MAX_FAILED_LOGIN_ATTEMPTS - 1):
        await _wrong_password_attempt(client, env["admin_email"])

    locked_resp = await client.post(
        "/api/v1/identity/auth/login", json={"email": env["admin_email"], "password": "wrong-1A!"}
    )
    assert "locked" in locked_resp.json()["detail"].lower()


async def test_successful_login_resets_failed_attempt_counter(client):
    env = await _bootstrap(client, f"Lockout-Reset-{unique_vat()[:6]}")

    for _ in range(AuthenticationService.MAX_FAILED_LOGIN_ATTEMPTS - 1):
        await _wrong_password_attempt(client, env["admin_email"])

    good_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": env["admin_email"], "password": env["admin_password"]},
    )
    assert good_resp.status_code == 200

    # The near-lockout streak must not carry over: another full run of
    # MAX_FAILED_LOGIN_ATTEMPTS-1 wrong guesses still must not lock it.
    for _ in range(AuthenticationService.MAX_FAILED_LOGIN_ATTEMPTS - 1):
        status = await _wrong_password_attempt(client, env["admin_email"])
        assert status == 401

    still_ok_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": env["admin_email"], "password": env["admin_password"]},
    )
    assert still_ok_resp.status_code == 200


async def test_unknown_email_never_locks_or_leaks_state(client):
    email = unique_email()
    for _ in range(AuthenticationService.MAX_FAILED_LOGIN_ATTEMPTS + 2):
        resp = await client.post(
            "/api/v1/identity/auth/login", json={"email": email, "password": "whatever-1A!"}
        )
        assert resp.status_code == 401
        assert "locked" not in resp.json()["detail"].lower()


async def test_password_reset_clears_lockout(client):
    """P0-B's required 'secure reset/recovery behavior' — P0-A's reset flow
    doubles as the account-recovery path so lockout is never permanent."""
    from src.api.main import app
    from src.modules.identity.api.deps import get_mailer

    env = await _bootstrap(client, f"Lockout-Recovery-{unique_vat()[:6]}")

    for _ in range(AuthenticationService.MAX_FAILED_LOGIN_ATTEMPTS):
        await _wrong_password_attempt(client, env["admin_email"])

    locked_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": env["admin_email"], "password": env["admin_password"]},
    )
    assert locked_resp.status_code == 401
    assert "locked" in locked_resp.json()["detail"].lower()

    sent = []

    async def fake_mailer(*, to, subject, body, attachments=None):
        sent.append(body)

    app.dependency_overrides[get_mailer] = lambda: fake_mailer
    try:
        await client.post(
            "/api/v1/identity/auth/password-reset/request", json={"email": env["admin_email"]}
        )
    finally:
        app.dependency_overrides.pop(get_mailer, None)

    paragraphs = [p.strip() for p in sent[0].split("\n\n") if p.strip()]
    raw_token = next(p for p in paragraphs if " " not in p and len(p) > 20)

    new_password = "Rec0very!Pass9"
    confirm_resp = await client.post(
        "/api/v1/identity/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": new_password},
    )
    assert confirm_resp.status_code == 200

    # No lingering lockout — immediate login with the new password works.
    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": env["admin_email"], "password": new_password},
    )
    assert login_resp.status_code == 200


async def test_wrong_totp_counts_toward_lockout(client):
    import pyotp

    label = f"Lockout-2FA-{unique_vat()[:6]}"
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
    company_id = boot_resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}

    setup_resp = await client.post("/api/v1/identity/me/2fa/setup", headers=headers)
    assert setup_resp.status_code == 200
    secret = setup_resp.json()["secret"]

    valid_code = pyotp.TOTP(secret).now()
    verify_resp = await client.post(
        "/api/v1/identity/me/2fa/verify", json={"totp_code": valid_code}, headers=headers
    )
    assert verify_resp.status_code == 200

    for _ in range(AuthenticationService.MAX_FAILED_LOGIN_ATTEMPTS):
        resp = await client.post(
            "/api/v1/identity/auth/login/verify-2fa",
            json={
                "email": payload["admin_email"],
                "password": payload["admin_password"],
                "totp_code": "000000",
            },
        )
        assert resp.status_code == 401

    valid_code_2 = pyotp.TOTP(secret).now()
    locked_resp = await client.post(
        "/api/v1/identity/auth/login/verify-2fa",
        json={
            "email": payload["admin_email"],
            "password": payload["admin_password"],
            "totp_code": valid_code_2,
        },
    )
    assert locked_resp.status_code == 401
    assert "locked" in locked_resp.json()["detail"].lower()
