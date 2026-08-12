"""Root-cause regression for the bug found live while verifying the Fixed
Assets Categories screen: `seed_core_data()`'s Admin-role permission sync
was a silent no-op under RLS (see migrations `a5b6c7d8e9f0` for the
one-time repair and `b6c7d8e9f0a1` for the permanent fix — a narrow,
additive `role_permission_admin_sync_read`/`_write` escape hatch mirroring
`set_login_lookup`'s proven pattern for `user_company_access`).

This proves the permanent fix actually works: simulate "a permission was
added to the catalog after this company was bootstrapped" by deleting one
row from an existing Admin role's `role_permission`, then re-running
`seed_core_data()` exactly as API startup does, and confirming the
permission comes back — without a manual migration.
"""

from sqlalchemy import text

from src.shared.infrastructure.db.seed import seed_core_data
from src.shared.infrastructure.db.session import AsyncSessionLocal, set_company_context
from tests.conftest import unique_email, unique_vat


async def test_admin_role_permission_sync_heals_drift_across_restart(client):
    payload = {
        "tenant_legal_name": "Admin Sync Holding",
        "company_legal_name": "Admin Sync Trading Co.",
        "company_legal_name_ar": "شركة اختبار مزامنة الصلاحيات",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Admin Sync Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201
    company_id = boot_resp.json()["company_id"]
    admin_role_id = boot_resp.json()["admin_role_id"]

    # Simulate drift: an Admin role that's missing one catalog permission
    # (the exact real-world shape found live — fixed_assets.category.manage
    # never reaching an existing company). Deleted through the same
    # company-scoped RLS path a real request would use, not bypassed.
    async with AsyncSessionLocal() as session:
        await set_company_context(session, company_id)
        target_permission_id = (
            await session.execute(
                text(
                    "SELECT permission_id FROM role_permission WHERE role_id = :rid LIMIT 1"
                ),
                {"rid": admin_role_id},
            )
        ).scalar_one()
        await session.execute(
            text("DELETE FROM role_permission WHERE role_id = :rid AND permission_id = :pid"),
            {"rid": admin_role_id, "pid": target_permission_id},
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        await set_company_context(session, company_id)
        missing_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM role_permission WHERE role_id = :rid AND permission_id = :pid"
                ),
                {"rid": admin_role_id, "pid": target_permission_id},
            )
        ).scalar_one()
        assert missing_count == 0, "setup failed: permission was not actually removed"

    # The real fix under test: exactly what API startup does (src/api/main.py's
    # lifespan), on a fresh session with no company context — the same
    # conditions the bug manifested under.
    async with AsyncSessionLocal() as session:
        await seed_core_data(session)

    async with AsyncSessionLocal() as session:
        await set_company_context(session, company_id)
        healed_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM role_permission WHERE role_id = :rid AND permission_id = :pid"
                ),
                {"rid": admin_role_id, "pid": target_permission_id},
            )
        ).scalar_one()
        assert healed_count == 1, "seed_core_data() did not heal the missing Admin-role permission"


async def test_admin_sync_policy_does_not_leak_without_the_flag(client):
    """The escape hatch is gated by `app.admin_sync` — without it set, the
    ordinary `company_isolation` policy still applies and a query against
    another company's role_permission still sees nothing, proving this
    fix didn't weaken RLS in general."""
    payload = {
        "tenant_legal_name": "Admin Sync Isolation Holding",
        "company_legal_name": "Admin Sync Isolation Co.",
        "company_legal_name_ar": "شركة اختبار عزل المزامنة",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "Isolation Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    admin_role_id = boot_resp.json()["admin_role_id"]

    async with AsyncSessionLocal() as session:
        # No set_company_context, no set_admin_sync — the exact "no context
        # at all" state a plain, unauthenticated connection would be in.
        # Explicitly set the nil-UUID sentinel rather than leaving the GUC
        # completely untouched: on a pooled connection already used by an
        # earlier test/request, current_setting(...) comes back '' (not
        # NULL) and role_permission's company_isolation policy's ::uuid
        # cast raises on that — same fix set_login_lookup/set_admin_sync
        # already apply for real request paths.
        await session.execute(
            text("SET LOCAL app.current_company_id = '00000000-0000-0000-0000-000000000000'")
        )
        count = (
            await session.execute(
                text("SELECT count(*) FROM role_permission WHERE role_id = :rid"), {"rid": admin_role_id}
            )
        ).scalar_one()
        assert count == 0
