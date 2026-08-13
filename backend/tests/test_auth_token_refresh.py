"""Owner-reported bug: the 30-minute access token had no renewal path at
all — the refresh token was minted at login and then never used for
anything server-side, so an idle session died hard with the only recovery
being a full manual logout/login. Closes the gap with POST /auth/refresh.
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
    company_id = boot_resp.json()["company_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    assert login_resp.status_code == 200
    body = login_resp.json()
    return {
        "company_id": company_id,
        "access_token": body["access_token"],
        "refresh_token": body["refresh_token"],
    }


async def test_refresh_with_valid_token_returns_a_new_pair(client):
    env = await _bootstrap(client, f"Refresh-Valid-{unique_vat()[:6]}")

    refresh_resp = await client.post(
        "/api/v1/identity/auth/refresh", json={"refresh_token": env["refresh_token"]}
    )
    assert refresh_resp.status_code == 200
    body = refresh_resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_new_access_token_from_refresh_actually_authenticates(client):
    env = await _bootstrap(client, f"Refresh-Works-{unique_vat()[:6]}")

    refresh_resp = await client.post(
        "/api/v1/identity/auth/refresh", json={"refresh_token": env["refresh_token"]}
    )
    new_access_token = refresh_resp.json()["access_token"]

    headers = {"Authorization": f"Bearer {new_access_token}", "X-Company-Id": env["company_id"]}
    me_resp = await client.get("/api/v1/identity/me", headers=headers)
    assert me_resp.status_code == 200


async def test_refresh_with_garbage_token_rejected(client):
    resp = await client.post("/api/v1/identity/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


async def test_refresh_with_access_token_instead_of_refresh_token_rejected(client):
    """An access token has type='access', not 'refresh' — the endpoint must
    reject it even though it's a structurally valid, correctly-signed JWT,
    otherwise a leaked access token could be used to mint an indefinite
    stream of fresh tokens past its own 30-minute lifetime."""
    env = await _bootstrap(client, f"Refresh-WrongType-{unique_vat()[:6]}")

    resp = await client.post(
        "/api/v1/identity/auth/refresh", json={"refresh_token": env["access_token"]}
    )
    assert resp.status_code == 401


async def test_refresh_does_not_require_a_company_header(client):
    """The whole point: this must work even when the access token (and any
    company context derived from it) has already expired — the refresh
    token is the only credential needed here."""
    env = await _bootstrap(client, f"Refresh-NoCompanyHeader-{unique_vat()[:6]}")

    resp = await client.post("/api/v1/identity/auth/refresh", json={"refresh_token": env["refresh_token"]})
    assert resp.status_code == 200
