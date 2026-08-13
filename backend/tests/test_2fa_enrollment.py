"""P0-3 (Phase-One audit closure) — 2FA Enrollment and Authentication Flow.

The audit found TOTP verification (`authenticate_step2_totp`,
`POST /auth/login/verify-2fa`) already real and already tested
(`test_login_lookup_integration.py::test_verify_2fa_succeeds_under_erp_app`
enables 2FA via raw SQL because — its own docstring says so — "No
enrollment endpoint exists in this API"). This file proves the other
half: a real user can now reach `is_2fa_enabled = true` through the
product itself, never SQL, and that reaching it doesn't change any of
the already-correct login/challenge behavior.
"""

import pyotp

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
    company_id = boot_resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id}
    return {
        "company_id": company_id,
        "headers": headers,
        "email": payload["admin_email"],
        "password": payload["admin_password"],
    }


async def _second_user(client, headers, company_id: str) -> dict:
    email = unique_email()
    password = "Str0ng!Passw0rd"
    create_resp = await client.post(
        "/api/v1/identity/users",
        headers=headers,
        json={"email": email, "full_name": "Second User", "password": password, "company_id": company_id},
    )
    assert create_resp.status_code == 201
    login_resp = await client.post("/api/v1/identity/auth/login", json={"email": email, "password": password})
    token = login_resp.json()["access_token"]
    return {
        "headers": {"Authorization": f"Bearer {token}", "X-Company-Id": company_id},
        "email": email,
        "password": password,
        "id": create_resp.json()["id"],
    }


async def test_user_can_start_enrollment_for_own_account(client):
    """Requirement #1."""
    env = await _bootstrap(client, f"P0-3Start-{unique_vat()[:6]}")
    resp = await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["secret"]
    assert body["provisioning_uri"].startswith("otpauth://totp/")


async def test_secret_is_generated_correctly(client):
    """Requirement #2 — the returned secret is a real, valid base32 TOTP
    secret that pyotp can actually derive working codes from (not a
    placeholder string)."""
    env = await _bootstrap(client, f"P0-3Secret-{unique_vat()[:6]}")
    resp = await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    secret = resp.json()["secret"]
    code = pyotp.TOTP(secret).now()
    assert len(code) == 6
    assert code.isdigit()


async def test_invalid_totp_cannot_complete_enrollment(client):
    """Requirement #3."""
    env = await _bootstrap(client, f"P0-3Invalid-{unique_vat()[:6]}")
    await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])

    resp = await client.post(
        "/api/v1/identity/me/2fa/verify", headers=env["headers"], json={"totp_code": "000000"}
    )
    assert resp.status_code == 400

    profile = await client.get("/api/v1/identity/me", headers=env["headers"])
    assert profile.json()["is_2fa_enabled"] is False


async def test_valid_totp_completes_enrollment(client):
    """Requirement #4."""
    env = await _bootstrap(client, f"P0-3Valid-{unique_vat()[:6]}")
    setup_resp = await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    secret = setup_resp.json()["secret"]

    code = pyotp.TOTP(secret).now()
    verify_resp = await client.post(
        "/api/v1/identity/me/2fa/verify", headers=env["headers"], json={"totp_code": code}
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_2fa_enabled"] is True

    profile = await client.get("/api/v1/identity/me", headers=env["headers"])
    assert profile.json()["is_2fa_enabled"] is True


async def test_opening_enrollment_does_not_enable_2fa(client):
    """Requirement #5 — the literal instruction: starting/viewing setup
    must never itself flip the flag."""
    env = await _bootstrap(client, f"P0-3Open-{unique_vat()[:6]}")
    setup_resp = await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    assert setup_resp.status_code == 200

    profile = await client.get("/api/v1/identity/me", headers=env["headers"])
    assert profile.json()["is_2fa_enabled"] is False

    # Calling setup again (still unverified) still doesn't enable it.
    await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    profile_again = await client.get("/api/v1/identity/me", headers=env["headers"])
    assert profile_again.json()["is_2fa_enabled"] is False


async def test_user_cannot_enroll_another_users_2fa(client):
    """Requirement #6 — by construction, not by permission check: both
    endpoints only ever act on the caller's own JWT-derived user id, so
    User B enrolling never touches User A's account, and there is no
    request shape (no path/body user id param at all) through which User
    B could even attempt to target User A."""
    env = await _bootstrap(client, f"P0-3Cross-{unique_vat()[:6]}")
    user_b = await _second_user(client, env["headers"], env["company_id"])

    setup_resp = await client.post("/api/v1/identity/me/2fa/setup", headers=user_b["headers"])
    secret = setup_resp.json()["secret"]
    code = pyotp.TOTP(secret).now()
    verify_resp = await client.post(
        "/api/v1/identity/me/2fa/verify", headers=user_b["headers"], json={"totp_code": code}
    )
    assert verify_resp.status_code == 200

    # User B is now enrolled; the original admin (User A) is provably
    # unaffected.
    admin_profile = await client.get("/api/v1/identity/me", headers=env["headers"])
    assert admin_profile.json()["is_2fa_enabled"] is False
    b_profile = await client.get("/api/v1/identity/me", headers=user_b["headers"])
    assert b_profile.json()["is_2fa_enabled"] is True


async def test_company_and_user_isolation(client):
    """Requirement #7 — enrolling a user in Company A's session has no
    effect on a same-numbered but distinct user in Company B."""
    company_a = await _bootstrap(client, f"P0-3IsoA-{unique_vat()[:6]}")
    company_b = await _bootstrap(client, f"P0-3IsoB-{unique_vat()[:6]}")

    setup_resp = await client.post("/api/v1/identity/me/2fa/setup", headers=company_a["headers"])
    secret = setup_resp.json()["secret"]
    code = pyotp.TOTP(secret).now()
    await client.post("/api/v1/identity/me/2fa/verify", headers=company_a["headers"], json={"totp_code": code})

    a_profile = await client.get("/api/v1/identity/me", headers=company_a["headers"])
    assert a_profile.json()["is_2fa_enabled"] is True
    b_profile = await client.get("/api/v1/identity/me", headers=company_b["headers"])
    assert b_profile.json()["is_2fa_enabled"] is False


async def test_enabled_2fa_cannot_be_bypassed_at_login(client):
    """Requirement #8 — after real enrollment through this new flow (not
    SQL), a plain email+password login for that user issues NO token —
    only `requires_2fa: true` — exactly the same guarantee
    `test_login_lookup_integration.py` already proved for a SQL-seeded
    user, now proven for one that went through the real product flow."""
    env = await _bootstrap(client, f"P0-3Bypass-{unique_vat()[:6]}")
    setup_resp = await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    secret = setup_resp.json()["secret"]
    code = pyotp.TOTP(secret).now()
    await client.post("/api/v1/identity/me/2fa/verify", headers=env["headers"], json={"totp_code": code})

    login_resp = await client.post(
        "/api/v1/identity/auth/login", json={"email": env["email"], "password": env["password"]}
    )
    assert login_resp.status_code == 200
    assert login_resp.json() == {"requires_2fa": True}
    assert "access_token" not in login_resp.json()

    # The real second factor completes it.
    verify_login = await client.post(
        "/api/v1/identity/auth/login/verify-2fa",
        json={"email": env["email"], "password": env["password"], "totp_code": pyotp.TOTP(secret).now()},
    )
    assert verify_login.status_code == 200
    assert verify_login.json()["access_token"]


async def test_invalid_login_challenge_is_rejected(client):
    """Requirement #9."""
    env = await _bootstrap(client, f"P0-3BadChallenge-{unique_vat()[:6]}")
    setup_resp = await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    secret = setup_resp.json()["secret"]
    code = pyotp.TOTP(secret).now()
    await client.post("/api/v1/identity/me/2fa/verify", headers=env["headers"], json={"totp_code": code})

    bad_resp = await client.post(
        "/api/v1/identity/auth/login/verify-2fa",
        json={"email": env["email"], "password": env["password"], "totp_code": "000000"},
    )
    assert bad_resp.status_code == 401
    assert "access_token" not in bad_resp.json()


async def test_totp_secret_never_leaked_in_ordinary_responses(client):
    """Requirement #10 — /me, /users, and /users/{id} all expose
    `is_2fa_enabled` but never the raw `totp_secret`, even for an
    enrolled user."""
    env = await _bootstrap(client, f"P0-3Leak-{unique_vat()[:6]}")
    setup_resp = await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    secret = setup_resp.json()["secret"]
    code = pyotp.TOTP(secret).now()
    await client.post("/api/v1/identity/me/2fa/verify", headers=env["headers"], json={"totp_code": code})

    me = await client.get("/api/v1/identity/me", headers=env["headers"])
    assert "totp_secret" not in me.json()
    assert me.json()["is_2fa_enabled"] is True

    users_list = await client.get("/api/v1/identity/users", headers=env["headers"])
    assert users_list.status_code == 200
    for row in users_list.json():
        assert "totp_secret" not in row

    admin_id = users_list.json()[0]["id"]
    detail = await client.get(f"/api/v1/identity/users/{admin_id}", headers=env["headers"])
    assert "totp_secret" not in detail.json()


async def test_users_without_2fa_authenticate_normally(client):
    """Requirement #11 — a user who never enrolls keeps logging in with a
    single step, exactly as before this change."""
    env = await _bootstrap(client, f"P0-3NoOp-{unique_vat()[:6]}")
    login_resp = await client.post(
        "/api/v1/identity/auth/login", json={"email": env["email"], "password": env["password"]}
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


async def test_cannot_verify_enrollment_that_was_never_started(client):
    """Edge case backing requirement #3/#5: no pending secret at all
    (never called setup) is a clean, safe rejection, not a crash."""
    env = await _bootstrap(client, f"P0-3NeverStarted-{unique_vat()[:6]}")
    resp = await client.post(
        "/api/v1/identity/me/2fa/verify", headers=env["headers"], json={"totp_code": "123456"}
    )
    assert resp.status_code == 400


async def test_cannot_restart_enrollment_once_already_enabled(client):
    """Safety policy decided during this task's design (not an
    invented business rule — there is no disable-2FA endpoint yet to
    recover from a rotated secret stranding an active authenticator):
    starting a fresh enrollment is blocked once 2FA is already on."""
    env = await _bootstrap(client, f"P0-3Restart-{unique_vat()[:6]}")
    setup_resp = await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    secret = setup_resp.json()["secret"]
    code = pyotp.TOTP(secret).now()
    await client.post("/api/v1/identity/me/2fa/verify", headers=env["headers"], json={"totp_code": code})

    second_setup = await client.post("/api/v1/identity/me/2fa/setup", headers=env["headers"])
    assert second_setup.status_code == 409
