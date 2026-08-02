"""Phase 17C-RLS Step 3A: integration verification for the real HTTP
bootstrap -> login -> 2FA-verify flow, through the app_user_login_lookup /
user_company_access_login_lookup RLS policies and the real erp_app runtime
role — no mocked repository, no superuser, no bypass.

There is no self-service "enable 2FA" endpoint in this API (confirmed by
grep — `verify_2fa` is the only 2FA-related route), so the 2FA test below
enables it directly via one raw SQL UPDATE (test setup data, same class of
thing as every other fixture in this suite) and generates a real, valid
TOTP code with `pyotp` against that secret, then calls the actual
`POST /auth/login/verify-2fa` endpoint — nothing about the endpoint or the
RLS layer itself is mocked.
"""

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.api.main import app
from src.shared.infrastructure.db.session import engine
from tests.conftest import unique_email, unique_vat

pytestmark = pytest.mark.asyncio


async def _bootstrap(client: AsyncClient) -> dict:
    payload = {
        "tenant_legal_name": "LoginIntegration Holding",
        "company_legal_name": "LoginIntegration Trading Co.",
        "company_legal_name_ar": "LoginIntegration Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "LoginIntegration Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return {**body, "email": payload["admin_email"], "password": payload["admin_password"]}


async def test_bootstrap_succeeds_under_erp_app():
    """Confirms the set_company_context() fix (already applied, prior to
    Step 3A) is still intact: tenant, company, role, and user_company_access
    all get created with no RLS violation under the real erp_app role."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        boot = await _bootstrap(client)
        assert boot["tenant_id"]
        assert boot["company_id"]
        assert boot["admin_user_id"]
        assert boot["admin_role_id"]


async def test_login_succeeds_under_erp_app_and_returns_authorized_companies():
    """The user-by-email lookup (app_user_login_lookup) and the
    authorized-companies lookup for token issuance
    (user_company_access_login_lookup) both work under real RLS
    enforcement — confirmed by decoding the issued JWT's own claim, the
    same thing get_auth_context() relies on for every subsequent request."""
    from src.shared.security.jwt import decode_token

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        boot = await _bootstrap(client)

        login_resp = await client.post(
            "/api/v1/identity/auth/login", json={"email": boot["email"], "password": boot["password"]}
        )
        assert login_resp.status_code == 200, login_resp.text
        tokens = login_resp.json()
        assert tokens["access_token"]
        assert tokens["refresh_token"]

        payload = decode_token(tokens["access_token"])
        authorized = payload.get("authorized_companies", [])
        assert any(entry == boot["company_id"] or entry.startswith(f"{boot['company_id']}:") for entry in authorized), (
            "issued JWT has no authorized_companies entry for the bootstrap company — "
            "user_company_access_login_lookup regressed"
        )

        # And the token is actually usable for a normal authenticated call.
        headers = {"Authorization": f"Bearer {tokens['access_token']}", "X-Company-Id": boot["company_id"]}
        me_resp = await client.get("/api/v1/identity/me/permissions", headers=headers)
        assert me_resp.status_code == 200, me_resp.text
        assert len(me_resp.json()["permission_codes"]) > 0


async def test_login_wrong_password_rejected_not_crashed():
    """A real-world negative case through the same login_lookup path — must
    reject cleanly (401), not crash (500), confirming the RLS escape hatch
    doesn't turn failures into something worse than before."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        boot = await _bootstrap(client)
        resp = await client.post(
            "/api/v1/identity/auth/login", json={"email": boot["email"], "password": "WrongPassword123!"}
        )
        assert resp.status_code == 401


async def test_verify_2fa_succeeds_under_erp_app():
    """Real end-to-end 2FA verification. No enrollment endpoint exists in
    this API, so 2FA is enabled directly via SQL (test setup only — the
    endpoint and RLS layer under test are untouched), then a real TOTP code
    is generated and submitted to the real verify-2fa endpoint."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        boot = await _bootstrap(client)

        totp_secret = pyotp.random_base32()
        async with engine.connect() as conn:
            trans = await conn.begin()
            await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{boot['tenant_id']}'"))
            result = await conn.execute(
                text(
                    "UPDATE app_user SET is_2fa_enabled = true, totp_secret = :secret WHERE id = :id"
                ),
                {"secret": totp_secret, "id": boot["admin_user_id"]},
            )
            assert result.rowcount == 1
            await trans.commit()

        step1_resp = await client.post(
            "/api/v1/identity/auth/login", json={"email": boot["email"], "password": boot["password"]}
        )
        assert step1_resp.status_code == 200
        assert step1_resp.json() == {"requires_2fa": True}

        code = pyotp.TOTP(totp_secret).now()
        step2_resp = await client.post(
            "/api/v1/identity/auth/login/verify-2fa",
            json={"email": boot["email"], "password": boot["password"], "totp_code": code},
        )
        assert step2_resp.status_code == 200, step2_resp.text
        assert step2_resp.json()["access_token"]

        # Cleanup: this test committed the 2FA UPDATE (RLS's WITH CHECK
        # needs a real transaction to persist across the two separate HTTP
        # calls above, each on its own connection) — undo it so no
        # unrelated test in this suite sees a 2FA-enabled bootstrap user.
        async with engine.connect() as conn:
            trans = await conn.begin()
            await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{boot['tenant_id']}'"))
            await conn.execute(
                text("UPDATE app_user SET is_2fa_enabled = false, totp_secret = NULL WHERE id = :id"),
                {"id": boot["admin_user_id"]},
            )
            await trans.commit()
