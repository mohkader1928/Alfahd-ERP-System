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
