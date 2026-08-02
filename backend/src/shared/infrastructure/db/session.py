"""Async DB session factory + Row-Level Security tenant context (Phase 7 §1.4).

`get_db` is the FastAPI dependency every module's repository layer uses. It
does NOT set the tenant context itself — that happens in
`tenant_context_middleware` once the request's AuthContext is known, via
`set_tenant_context`. This keeps the DB layer ignorant of HTTP concerns.
"""

from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.shared.config.settings import get_settings

settings = get_settings()

# Phase 17C-RLS Step 3A: the nil UUID, used only as a non-matching sentinel
# for app.current_tenant_id/app.current_company_id during the login lookup
# — see set_login_lookup()'s docstring for why this is needed at all.
_NIL_UUID = UUID(int=0)

engine = create_async_engine(settings.database_url, pool_pre_ping=True, echo=False)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id: UUID) -> None:
    """Set the RLS session variable read by every `tenant_id`-scoped table's
    `tenant_isolation` policy (M0 tables: company, branch, app_user, ...).

    Uses SET LOCAL so the value is scoped to the current transaction only —
    it never leaks to a pooled connection's next user. SET does not support
    bind parameters over the extended query protocol, so the value is
    interpolated directly; this is safe because `tenant_id` is a `UUID`
    instance (not raw user input) and `str(UUID(...))` can only ever produce
    the fixed `[0-9a-f-]` hex-and-hyphen format.
    """
    await session.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))


async def set_company_context(session: AsyncSession, company_id: UUID) -> None:
    """Set the RLS session variable for `company_id`-scoped tables (accounting,
    and every module after it — those tables have no `tenant_id` column of
    their own, per Phase 7 §3). Same SET LOCAL / interpolation rationale as
    `set_tenant_context` above.
    """
    await session.execute(text(f"SET LOCAL app.current_company_id = '{company_id}'"))


async def set_login_lookup(session: AsyncSession) -> None:
    """Phase 17C-RLS Step 3A: transaction-local escape hatch for the
    unauthenticated login/2FA-verify user-by-email lookup, which by
    definition runs before any tenant/company context can exist. Gates two
    additive, SELECT-only policies (see docs/17c-rls-runtime-role-hardening.md):
    `app_user_login_lookup` (the by-email lookup itself) and
    `user_company_access_login_lookup` (needed right after, for
    `issue_tokens()` to list which companies the new JWT should authorize —
    same "context not known yet" problem, same fix). Neither affects
    INSERT/UPDATE/DELETE, and neither touches the existing
    `tenant_isolation`/`company_isolation` policies at all.

    Also (re-)sets `app.current_tenant_id`/`app.current_company_id` to the
    nil UUID. This is not an RLS decision — `app_user_login_lookup` and
    `user_company_access_login_lookup` are what actually grant access, via
    the `app.login_lookup` flag alone. It's a connection-pool safety fix,
    empirically required: PostgreSQL creates a persistent per-connection
    placeholder the first time a custom GUC name is referenced (e.g. by any
    prior authenticated request on this same pooled connection calling
    `set_tenant_context`); once that placeholder exists, ending that
    transaction resets the GUC to an empty string, not back to NULL, for
    the rest of that physical connection's life. `tenant_isolation`'s
    `current_setting(...)::uuid` cast raises a hard error on `''` — and
    since Postgres OR's permissive policies together, that raises *before*
    `app_user_login_lookup`'s own clause is even reached, crashing login on
    any previously-used pooled connection regardless of this fix. Setting
    a syntactically valid (nil) UUID sentinel here avoids the cast error
    without touching `tenant_isolation` at all; the sentinel is guaranteed
    to never match a real tenant/company, so it never grants anything by
    itself — grep this file's tests for the empirical proof.

    SET LOCAL ties all of this to the current transaction only, same as
    `set_tenant_context`/`set_company_context` above; none of it survives
    past this request's COMMIT/ROLLBACK on a pooled connection. Call this
    ONLY from the login/verify-2fa route handlers, immediately before the
    call that performs the by-email lookup — never from a general-purpose
    repository method, so no other code path can trigger it.
    """
    await session.execute(text("SET LOCAL app.login_lookup = 'true'"))
    await session.execute(text(f"SET LOCAL app.current_tenant_id = '{_NIL_UUID}'"))
    await session.execute(text(f"SET LOCAL app.current_company_id = '{_NIL_UUID}'"))
