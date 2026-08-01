"""Per-request AuthContext: resolves the JWT + X-Company-Id/X-Branch-Id headers
into a validated (user, tenant, company, branch) scope, per Phase 10 §2 and
FR-CORE-003/004. Also sets the PostgreSQL RLS session variable so tenant
isolation is enforced at the database layer, not just in application code.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.infrastructure.db.session import get_db, set_company_context, set_tenant_context
from src.shared.security.jwt import TokenError, decode_token


@dataclass(frozen=True)
class AuthContext:
    user_id: UUID
    tenant_id: UUID
    company_id: UUID
    branch_id: UUID | None


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or malformed Authorization header")
    return authorization.split(" ", 1)[1]


async def get_auth_context(
    authorization: str | None = Header(default=None),
    x_company_id: str | None = Header(default=None, alias="X-Company-Id"),
    x_branch_id: str | None = Header(default=None, alias="X-Branch-Id"),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    token = _extract_bearer_token(authorization)
    try:
        payload = decode_token(token)
    except TokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")

    if not x_company_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Company-Id header is required")

    authorized_companies: list[str] = payload.get("authorized_companies", [])
    # Each entry is "<company_id>" (whole company) or "<company_id>:<branch_id>" (branch-scoped)
    company_authorized = any(
        entry == x_company_id or entry.startswith(f"{x_company_id}:") for entry in authorized_companies
    )
    if not company_authorized:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this company")

    if x_branch_id:
        branch_authorized = (
            f"{x_company_id}:{x_branch_id}" in authorized_companies or x_company_id in authorized_companies
        )
        if not branch_authorized:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this branch")

    ctx = AuthContext(
        user_id=UUID(payload["sub"]),
        tenant_id=UUID(payload["tenant_id"]),
        company_id=UUID(x_company_id),
        branch_id=UUID(x_branch_id) if x_branch_id else None,
    )

    # Phase 7 §1.4: belt-and-suspenders DB-level isolation via RLS.
    # Two session variables because the envelope differs by table (Phase 7 §3):
    # identity's root tables carry tenant_id, every module after it carries
    # only company_id.
    await set_tenant_context(db, ctx.tenant_id)
    await set_company_context(db, ctx.company_id)

    return ctx


async def require_branch_context(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Use in place of `get_auth_context` for any endpoint that creates a
    branch-scoped document (FR-CORE-002: every document belongs to a
    specific branch). `AuthContext.branch_id` is optional at the identity
    layer (company-wide access is valid for admin/reporting endpoints), but
    document-creation endpoints must reject a missing X-Branch-Id rather
    than silently writing a NULL into a NOT NULL column.
    """
    if ctx.branch_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Branch-Id header is required for this operation")
    return ctx
