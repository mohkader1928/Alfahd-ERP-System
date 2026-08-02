"""Phase 17C-RLS: direct database-layer proof that Row-Level Security is
actually enforced for the real application runtime role.

Every other security test in this suite (test_multi_tenancy_isolation.py)
goes through the HTTP/API boundary — proving what an attacker could or
couldn't reach through the application. This file is different on purpose:
it connects with raw SQL through the *exact* engine the API and Celery
worker use (`src.shared.infrastructure.db.session.engine`, i.e. whatever
`DATABASE_URL` in the running environment's `.env` points at — the
`erp_app` role after Phase 17C-RLS, never a throwaway role created just for
this test), and asserts what Postgres itself does when that role's session
sets (or fails to set) `app.current_company_id` / `app.current_tenant_id`.

Before Phase 17C-RLS, `erp_app` did not exist and the API connected as
`erp`, a full Postgres superuser (`rolbypassrls=true`) — every query below
would have silently succeeded regardless of RLS policy, because superusers
bypass RLS unconditionally. If this file is ever run against a superuser
connection again, every cross-company assertion here will fail loudly
(rows that should be invisible will be visible), which is the point: it's
a regression test for the *database-level* guarantee, not just the
application-level one.

Every test runs its setup and assertions inside one transaction that is
always rolled back, never committed — no persistent data, and no need for
per-test cleanup. `journal_entry_line`'s deferred balance-check trigger
(461205cf56a6) only fires on COMMIT, so an intentionally single-sided debit
line never trips it here.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.shared.infrastructure.db.session import engine, set_login_lookup

pytestmark = pytest.mark.asyncio


async def _set_tenant(conn, tenant_id) -> None:
    # SET LOCAL does not support bind parameters over the extended query
    # protocol (see session.py's set_tenant_context) — interpolation is
    # safe here because tenant_id is always a uuid.UUID instance.
    await conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))


async def _set_company(conn, company_id) -> None:
    await conn.execute(text(f"SET LOCAL app.current_company_id = '{company_id}'"))


async def _clear_tenant(conn) -> None:
    await conn.execute(text("RESET app.current_tenant_id"))


async def _make_tenant_and_company(conn, label: str) -> dict:
    """Creates one tenant + company + a full accounting chain (account_type,
    account x2, journal, journal_entry) for it, all uncommitted. Returns the
    ids needed to build company-scoped rows and to switch context."""
    tenant_id = (
        await conn.execute(text("INSERT INTO tenant (legal_name) VALUES (:n) RETURNING id"), {"n": f"{label} Tenant"})
    ).scalar_one()

    currency_id = (await conn.execute(text("SELECT id FROM currency WHERE code = 'SAR'"))).scalar_one_or_none()
    if currency_id is None:
        currency_id = (
            await conn.execute(
                text("INSERT INTO currency (code, symbol) VALUES ('SAR', 'SAR') RETURNING id")
            )
        ).scalar_one()

    await _set_tenant(conn, tenant_id)
    vat = str(uuid.uuid4().int)[:15]
    company_id = (
        await conn.execute(
            text(
                """
                INSERT INTO company
                    (tenant_id, legal_name, legal_name_ar, vat_number, base_currency_id, valuation_method)
                VALUES (:tenant_id, :name, :name_ar, :vat, :currency_id, 'fifo')
                RETURNING id
                """
            ),
            {"tenant_id": str(tenant_id), "name": f"{label} Co", "name_ar": f"{label} Co AR", "vat": vat, "currency_id": str(currency_id)},
        )
    ).scalar_one()
    await _clear_tenant(conn)

    await _set_company(conn, company_id)

    account_type_id = (await conn.execute(text("SELECT id FROM account_type WHERE code = 'asset'"))).scalar_one_or_none()
    if account_type_id is None:
        account_type_id = (
            await conn.execute(text("INSERT INTO account_type (code) VALUES ('asset') RETURNING id"))
        ).scalar_one()

    cash_account_id = (
        await conn.execute(
            text(
                "INSERT INTO account (company_id, code, name, account_type_id) "
                "VALUES (:co, :code, 'Cash', :at) RETURNING id"
            ),
            {"co": str(company_id), "code": f"CASH-{uuid.uuid4().hex[:6]}", "at": str(account_type_id)},
        )
    ).scalar_one()

    journal_id = (
        await conn.execute(
            text("INSERT INTO journal (company_id, code, name) VALUES (:co, :code, 'General') RETURNING id"),
            {"co": str(company_id), "code": f"GJ-{uuid.uuid4().hex[:6]}"},
        )
    ).scalar_one()

    journal_entry_id = (
        await conn.execute(
            text(
                "INSERT INTO journal_entry (company_id, journal_id, entry_date, created_by) "
                "VALUES (:co, :journal_id, '2026-08-01', :created_by) RETURNING id"
            ),
            {"co": str(company_id), "journal_id": str(journal_id), "created_by": str(uuid.uuid4())},
        )
    ).scalar_one()

    return {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "cash_account_id": cash_account_id,
        "journal_entry_id": journal_entry_id,
    }


async def _make_product_category(conn, company_id) -> uuid.UUID:
    await _set_company(conn, company_id)
    return (
        await conn.execute(
            text("INSERT INTO product_category (company_id, name) VALUES (:co, :name) RETURNING id"),
            {"co": str(company_id), "name": f"Category {uuid.uuid4().hex[:6]}"},
        )
    ).scalar_one()


async def _make_unit_of_measure(conn, company_id) -> uuid.UUID:
    await _set_company(conn, company_id)
    return (
        await conn.execute(
            text("INSERT INTO unit_of_measure (company_id, name, code) VALUES (:co, :name, :code) RETURNING id"),
            {"co": str(company_id), "name": f"Unit {uuid.uuid4().hex[:6]}", "code": f"U{uuid.uuid4().hex[:6]}"},
        )
    ).scalar_one()


async def _make_product(conn, tenant_id, company_id) -> uuid.UUID:
    await _set_company(conn, company_id)
    return (
        await conn.execute(
            text(
                "INSERT INTO product (tenant_id, company_id, sku, name) "
                "VALUES (:tenant_id, :co, :sku, :name) RETURNING id"
            ),
            {"tenant_id": str(tenant_id), "co": str(company_id), "sku": f"SKU-{uuid.uuid4().hex[:8]}", "name": "Widget"},
        )
    ).scalar_one()


async def _make_journal_entry_line(conn, company_id, journal_entry_id, account_id) -> uuid.UUID:
    await _set_company(conn, company_id)
    return (
        await conn.execute(
            text(
                "INSERT INTO journal_entry_line (journal_entry_id, account_id, company_id, debit, credit) "
                "VALUES (:je, :acct, :co, 100, 0) RETURNING id"
            ),
            {"je": str(journal_entry_id), "acct": str(account_id), "co": str(company_id)},
        )
    ).scalar_one()


@pytest.fixture
async def two_companies():
    """Yields (conn, a, b) where a/b carry ids for a fully independent
    tenant+company+accounting-chain pair, all inside one uncommitted
    transaction on the real erp_app-authenticated engine. Always rolled
    back — nothing here is ever persisted."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            a = await _make_tenant_and_company(conn, "Alpha")
            b = await _make_tenant_and_company(conn, "Beta")
            yield conn, a, b
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------
# product_category
# ---------------------------------------------------------------------------


async def test_product_category_select_isolation(two_companies):
    conn, a, b = two_companies
    cat_a = await _make_product_category(conn, a["company_id"])
    cat_b = await _make_product_category(conn, b["company_id"])

    await _set_company(conn, a["company_id"])
    rows = (await conn.execute(text("SELECT id FROM product_category"))).scalars().all()
    assert cat_a in rows
    assert cat_b not in rows


async def test_product_category_update_isolation(two_companies):
    conn, a, b = two_companies
    cat_b = await _make_product_category(conn, b["company_id"])

    await _set_company(conn, a["company_id"])
    result = await conn.execute(
        text("UPDATE product_category SET name = 'hacked' WHERE id = :id"), {"id": str(cat_b)}
    )
    assert result.rowcount == 0

    await _set_company(conn, b["company_id"])
    name = (await conn.execute(text("SELECT name FROM product_category WHERE id = :id"), {"id": str(cat_b)})).scalar_one()
    assert name != "hacked"


async def test_product_category_delete_isolation(two_companies):
    conn, a, b = two_companies
    cat_b = await _make_product_category(conn, b["company_id"])

    await _set_company(conn, a["company_id"])
    result = await conn.execute(text("DELETE FROM product_category WHERE id = :id"), {"id": str(cat_b)})
    assert result.rowcount == 0

    await _set_company(conn, b["company_id"])
    still_there = (
        await conn.execute(text("SELECT 1 FROM product_category WHERE id = :id"), {"id": str(cat_b)})
    ).scalar_one_or_none()
    assert still_there == 1


async def test_product_category_insert_isolation_rejected(two_companies):
    conn, a, b = two_companies
    await _set_company(conn, a["company_id"])
    with pytest.raises(DBAPIError, match="row-level security"):
        await conn.execute(
            text("INSERT INTO product_category (company_id, name) VALUES (:co, 'x')"), {"co": str(b["company_id"])}
        )


# ---------------------------------------------------------------------------
# unit_of_measure
# ---------------------------------------------------------------------------


async def test_unit_of_measure_select_isolation(two_companies):
    conn, a, b = two_companies
    uom_a = await _make_unit_of_measure(conn, a["company_id"])
    uom_b = await _make_unit_of_measure(conn, b["company_id"])

    await _set_company(conn, a["company_id"])
    rows = (await conn.execute(text("SELECT id FROM unit_of_measure"))).scalars().all()
    assert uom_a in rows
    assert uom_b not in rows


async def test_unit_of_measure_update_isolation(two_companies):
    conn, a, b = two_companies
    uom_b = await _make_unit_of_measure(conn, b["company_id"])

    await _set_company(conn, a["company_id"])
    result = await conn.execute(text("UPDATE unit_of_measure SET name = 'hacked' WHERE id = :id"), {"id": str(uom_b)})
    assert result.rowcount == 0


async def test_unit_of_measure_insert_isolation_rejected(two_companies):
    conn, a, b = two_companies
    await _set_company(conn, a["company_id"])
    with pytest.raises(DBAPIError, match="row-level security"):
        await conn.execute(
            text("INSERT INTO unit_of_measure (company_id, name, code) VALUES (:co, 'x', 'X1')"),
            {"co": str(b["company_id"])},
        )


# ---------------------------------------------------------------------------
# product
# ---------------------------------------------------------------------------


async def test_product_select_isolation(two_companies):
    conn, a, b = two_companies
    prod_a = await _make_product(conn, a["tenant_id"], a["company_id"])
    prod_b = await _make_product(conn, b["tenant_id"], b["company_id"])

    await _set_company(conn, a["company_id"])
    rows = (await conn.execute(text("SELECT id FROM product"))).scalars().all()
    assert prod_a in rows
    assert prod_b not in rows


async def test_product_delete_isolation(two_companies):
    conn, a, b = two_companies
    prod_b = await _make_product(conn, b["tenant_id"], b["company_id"])

    await _set_company(conn, a["company_id"])
    result = await conn.execute(text("DELETE FROM product WHERE id = :id"), {"id": str(prod_b)})
    assert result.rowcount == 0


async def test_product_insert_isolation_rejected(two_companies):
    conn, a, b = two_companies
    await _set_company(conn, a["company_id"])
    with pytest.raises(DBAPIError, match="row-level security"):
        await conn.execute(
            text("INSERT INTO product (tenant_id, company_id, sku, name) VALUES (:t, :co, 'X', 'X')"),
            {"t": str(b["tenant_id"]), "co": str(b["company_id"])},
        )


# ---------------------------------------------------------------------------
# journal_entry_line (Phase 16A)
# ---------------------------------------------------------------------------


async def test_journal_entry_line_select_isolation(two_companies):
    conn, a, b = two_companies
    line_a = await _make_journal_entry_line(conn, a["company_id"], a["journal_entry_id"], a["cash_account_id"])
    line_b = await _make_journal_entry_line(conn, b["company_id"], b["journal_entry_id"], b["cash_account_id"])

    await _set_company(conn, a["company_id"])
    rows = (await conn.execute(text("SELECT id FROM journal_entry_line"))).scalars().all()
    assert line_a in rows
    assert line_b not in rows


async def test_journal_entry_line_update_isolation(two_companies):
    conn, a, b = two_companies
    line_b = await _make_journal_entry_line(conn, b["company_id"], b["journal_entry_id"], b["cash_account_id"])

    await _set_company(conn, a["company_id"])
    result = await conn.execute(text("UPDATE journal_entry_line SET debit = 999 WHERE id = :id"), {"id": str(line_b)})
    assert result.rowcount == 0


async def test_journal_entry_line_delete_isolation(two_companies):
    conn, a, b = two_companies
    line_b = await _make_journal_entry_line(conn, b["company_id"], b["journal_entry_id"], b["cash_account_id"])

    await _set_company(conn, a["company_id"])
    result = await conn.execute(text("DELETE FROM journal_entry_line WHERE id = :id"), {"id": str(line_b)})
    assert result.rowcount == 0


async def test_journal_entry_line_insert_isolation_rejected(two_companies):
    conn, a, b = two_companies
    await _set_company(conn, a["company_id"])
    with pytest.raises(DBAPIError, match="row-level security"):
        await conn.execute(
            text(
                "INSERT INTO journal_entry_line (journal_entry_id, account_id, company_id, debit, credit) "
                "VALUES (:je, :acct, :co, 50, 0)"
            ),
            {"je": str(b["journal_entry_id"]), "acct": str(b["cash_account_id"]), "co": str(b["company_id"])},
        )


# ---------------------------------------------------------------------------
# company (tenant_isolation, the identity-root policy family — distinct from
# company_isolation, which every table above uses)
# ---------------------------------------------------------------------------


async def test_company_select_isolation_by_tenant(two_companies):
    conn, a, b = two_companies

    await _set_tenant(conn, a["tenant_id"])
    rows = (await conn.execute(text("SELECT id FROM company"))).scalars().all()
    assert a["company_id"] in rows
    assert b["company_id"] not in rows
    await _clear_tenant(conn)


async def test_company_update_isolation_by_tenant(two_companies):
    conn, a, b = two_companies

    await _set_tenant(conn, a["tenant_id"])
    result = await conn.execute(
        text("UPDATE company SET legal_name = 'hacked' WHERE id = :id"), {"id": str(b["company_id"])}
    )
    assert result.rowcount == 0
    await _clear_tenant(conn)


# ---------------------------------------------------------------------------
# Bare SELECT / missing-context default-deny — the core RLS guarantee: no
# context set at all must mean zero rows visible, not "everything visible."
#
# These deliberately do NOT use the `two_companies` fixture's connection.
# Empirically confirmed while writing this file: PostgreSQL creates a
# persistent per-connection "placeholder" the first time a custom GUC name
# (like `app.current_company_id`) is referenced on a physical connection —
# after that, ROLLBACK reverts a `SET LOCAL` on it to an empty string, not
# back to genuinely unset/NULL, for the rest of that physical connection's
# life. Since `engine`'s pool is a session-wide singleton already used by
# every other test in this run, most pooled connections have that
# placeholder by now — reusing one would test "context was explicitly
# cleared" (a different, less interesting scenario: `''::uuid` raises
# immediately, which is a safe failure mode, just not the one being proven
# here) rather than "context was never set at all" (silent 0 rows). Calling
# `engine.dispose()` first forces a genuinely virgin connection — the same
# technique `zatca_tasks.py`'s `_run_with_fresh_pool` already uses per task,
# for this identical reason.
# ---------------------------------------------------------------------------


async def test_bare_select_without_any_context_returns_nothing():
    await engine.dispose()
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            rows = (await conn.execute(text("SELECT id FROM product_category"))).scalars().all()
            assert rows == [], "product_category returned rows with no RLS context ever set on this connection"
        finally:
            await trans.rollback()


async def test_missing_context_default_deny_across_all_five_tables():
    await engine.dispose()
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            for table in ("product_category", "unit_of_measure", "product", "journal_entry_line", "company"):
                rows = (await conn.execute(text(f"SELECT id FROM {table}"))).scalars().all()
                assert rows == [], f"{table} returned rows with no RLS context set — default-deny is broken"
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------
# app_user_login_lookup / user_company_access_login_lookup (Phase 17C-RLS
# Step 3A). `app_user` carries tenant_isolation RLS, but the unauthenticated
# login/2FA-verify lookup runs before any tenant is known — see migration
# f7004fe055a4 and set_login_lookup()'s docstring for the full rationale.
# These tests exercise the REAL `set_login_lookup()` helper (the exact
# function the login/verify-2fa routes call), not a reimplementation.
# ---------------------------------------------------------------------------


async def _make_app_user(conn, tenant_id) -> dict:
    await _set_tenant(conn, tenant_id)
    email = f"logintest-{uuid.uuid4().hex[:10]}@test-erp.sa"
    user_id = (
        await conn.execute(
            text(
                "INSERT INTO app_user (tenant_id, email, password_hash, full_name) "
                "VALUES (:tenant_id, :email, 'x', 'Login Test User') RETURNING id"
            ),
            {"tenant_id": str(tenant_id), "email": email},
        )
    ).scalar_one()
    return {"user_id": user_id, "email": email}


@pytest.fixture
async def tenant_with_user():
    """A single tenant + one app_user row. Lighter than `two_companies` —
    the login-lookup tests don't need a company/accounting chain at all.
    Uncommitted, always rolled back."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            tenant_id = (
                await conn.execute(text("INSERT INTO tenant (legal_name) VALUES ('LoginTest Tenant') RETURNING id"))
            ).scalar_one()
            user = await _make_app_user(conn, tenant_id)
            yield conn, tenant_id, user
        finally:
            await trans.rollback()


async def test_login_lookup_missing_context_returns_no_rows():
    """Test A: a genuinely fresh connection (see the comment on the two
    tests above for why `engine.dispose()` matters here), no
    app.current_tenant_id, no app.login_lookup — the by-email lookup the
    login endpoint performs must return nothing."""
    await engine.dispose()
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            rows = (
                await conn.execute(text("SELECT id FROM app_user WHERE email = :e"), {"e": "nobody@example.com"})
            ).scalars().all()
            assert rows == []
        finally:
            await trans.rollback()


async def test_login_lookup_enabled_finds_user_without_tenant_context(tenant_with_user):
    """Test B: with app.login_lookup active (via the real set_login_lookup()
    helper), the intended user is found by email — with no tenant context
    ever having been set for this check."""
    conn, _tenant_id, user = tenant_with_user
    await set_login_lookup(conn)
    row = (
        await conn.execute(text("SELECT id FROM app_user WHERE email = :e"), {"e": user["email"]})
    ).scalar_one_or_none()
    assert row == user["user_id"]


async def test_login_lookup_is_select_only(tenant_with_user):
    """Test C: app.login_lookup grants SELECT only — INSERT/UPDATE/DELETE on
    app_user remain governed solely by the untouched tenant_isolation
    policy, which set_login_lookup()'s nil-UUID sentinel can never satisfy."""
    conn, tenant_id, user = tenant_with_user
    await set_login_lookup(conn)

    # A raised RLS violation aborts the whole Postgres transaction for any
    # further statement until rolled back — scope it to a SAVEPOINT so the
    # UPDATE/DELETE checks below can still run in the same test.
    savepoint = await conn.begin_nested()
    try:
        with pytest.raises(DBAPIError, match="row-level security"):
            await conn.execute(
                text("INSERT INTO app_user (tenant_id, email, password_hash, full_name) VALUES (:t, :e, 'x', 'x')"),
                {"t": str(tenant_id), "e": f"other-{uuid.uuid4().hex[:8]}@test-erp.sa"},
            )
    finally:
        await savepoint.rollback()

    result = await conn.execute(
        text("UPDATE app_user SET full_name = 'hacked' WHERE id = :id"), {"id": str(user["user_id"])}
    )
    assert result.rowcount == 0

    result = await conn.execute(text("DELETE FROM app_user WHERE id = :id"), {"id": str(user["user_id"])})
    assert result.rowcount == 0


async def test_login_lookup_no_unrelated_table_bypass(tenant_with_user):
    """Test D: app.login_lookup = 'true' must not leak into tables that
    never defined a login_lookup-gated policy — one Phase 16A table
    (journal_entry_line), one Phase 17B table (product_category), plus
    `company` (tenant_isolation family, but not login-lookup-gated)."""
    conn, _tenant_id, _user = tenant_with_user
    await set_login_lookup(conn)
    for table in ("journal_entry_line", "product_category", "company"):
        rows = (await conn.execute(text(f"SELECT id FROM {table}"))).scalars().all()
        assert rows == [], f"{table} became visible via app.login_lookup — unrelated-table bypass"


async def test_tenant_isolation_still_works_normally_for_app_user(tenant_with_user):
    """Test E: ordinary authenticated access (real tenant context, no
    login_lookup) behaves exactly as tenant_isolation defined before Step
    3A — the new policy doesn't broaden it in any way."""
    conn, tenant_id, user = tenant_with_user

    await _set_tenant(conn, tenant_id)
    row = (
        await conn.execute(text("SELECT id FROM app_user WHERE email = :e"), {"e": user["email"]})
    ).scalar_one_or_none()
    assert row == user["user_id"]

    await _set_tenant(conn, uuid.uuid4())
    row2 = (
        await conn.execute(text("SELECT id FROM app_user WHERE email = :e"), {"e": user["email"]})
    ).scalar_one_or_none()
    assert row2 is None, "a different tenant's context found another tenant's user — tenant_isolation regressed"


async def test_login_lookup_does_not_leak_across_transactions():
    """Test F: SET LOCAL app.login_lookup = 'true' inside one transaction,
    rolled back, must not remain active for the next transaction on the
    same physical pooled connection — the exact custom-GUC persistence
    subtlety this phase already had to work around (see the module
    docstring and the two missing-context tests above)."""
    await engine.dispose()
    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("SET LOCAL app.login_lookup = 'true'"))
        active = (await conn.execute(text("SELECT current_setting('app.login_lookup', true)"))).scalar()
        assert active == "true"
        await trans.rollback()

        trans2 = await conn.begin()
        try:
            after = (await conn.execute(text("SELECT current_setting('app.login_lookup', true)"))).scalar()
            assert after != "true", "app.login_lookup leaked past ROLLBACK on a pooled connection"
            rows = (await conn.execute(text("SELECT id FROM app_user"))).scalars().all()
            assert rows == [], "app_user visible after login_lookup should have reset — leak across transactions"
        finally:
            await trans2.rollback()
