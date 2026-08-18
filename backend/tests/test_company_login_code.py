"""Hardening Issue #4 (Owner directive, 2026-08-18): a system-assigned
`company.code`, required at login alongside email/password on the real web
login screen. Optional at the API contract level (LoginRequest.company_code)
so the dozens of existing tests/integrations that never send it are
unaffected -- validated (and rejected if wrong) only when provided.
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
    body = boot_resp.json()
    return {**payload, "company_id": body["company_id"], "company_code": body["company_code"]}


async def test_bootstrap_returns_a_company_code(client):
    env = await _bootstrap(client, f"CodeGen-{unique_vat()[:6]}")
    assert env["company_code"]
    assert len(env["company_code"]) == 6
    # hex charset only (0-9, A-F) -- no ambiguous I/L/O characters.
    assert all(c in "0123456789ABCDEF" for c in env["company_code"])


async def test_two_companies_get_different_codes(client):
    env_a = await _bootstrap(client, f"CodeUniq-A-{unique_vat()[:6]}")
    env_b = await _bootstrap(client, f"CodeUniq-B-{unique_vat()[:6]}")
    assert env_a["company_code"] != env_b["company_code"]


async def test_login_with_correct_company_code_succeeds(client):
    env = await _bootstrap(client, f"CodeLoginOK-{unique_vat()[:6]}")
    resp = await client.post(
        "/api/v1/identity/auth/login",
        json={
            "email": env["admin_email"],
            "password": env["admin_password"],
            "company_code": env["company_code"],
        },
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_with_correct_company_code_is_case_insensitive(client):
    env = await _bootstrap(client, f"CodeLoginCase-{unique_vat()[:6]}")
    resp = await client.post(
        "/api/v1/identity/auth/login",
        json={
            "email": env["admin_email"],
            "password": env["admin_password"],
            "company_code": env["company_code"].lower(),
        },
    )
    assert resp.status_code == 200


async def test_login_with_wrong_company_code_is_rejected(client):
    env = await _bootstrap(client, f"CodeLoginWrong-{unique_vat()[:6]}")
    resp = await client.post(
        "/api/v1/identity/auth/login",
        json={
            "email": env["admin_email"],
            "password": env["admin_password"],
            "company_code": "ZZZZZZ",
        },
    )
    assert resp.status_code == 401
    detail = resp.json()["detail"].lower()
    # Anti-enumeration: the message must not reveal that email+password
    # were actually correct and only the company code was wrong.
    assert "company code" not in detail or "invalid email" in detail


async def test_login_with_another_companys_code_is_rejected(client):
    """The classic case this feature exists for: correct email+password,
    but the code typed belongs to a DIFFERENT real company."""
    env_a = await _bootstrap(client, f"CodeCross-A-{unique_vat()[:6]}")
    env_b = await _bootstrap(client, f"CodeCross-B-{unique_vat()[:6]}")

    resp = await client.post(
        "/api/v1/identity/auth/login",
        json={
            "email": env_a["admin_email"],
            "password": env_a["admin_password"],
            "company_code": env_b["company_code"],
        },
    )
    assert resp.status_code == 401


async def test_login_without_company_code_still_works(client):
    """Backward compatibility: omitting the field entirely (existing
    integrations, mobile clients not yet updated, etc.) must keep working
    exactly as before -- only the real web login screen makes it required,
    client-side."""
    env = await _bootstrap(client, f"CodeOptional-{unique_vat()[:6]}")
    resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": env["admin_email"], "password": env["admin_password"]},
    )
    assert resp.status_code == 200
