"""FastAPI routes for Notifications — a personal inbox, not a company-wide
resource, so these are gated only by authentication (any company member
sees their own notifications), matching how every reference ERP treats a
user's own alert feed. No `require_permission` gate is needed since RLS
plus the `recipient_user_id == ctx.user_id` filter already scope every
query to exactly what this user is allowed to see."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.api.deps import get_notification_repo
from src.modules.notifications.api.schemas import NotificationOut, UnreadCountOut
from src.modules.notifications.infrastructure.repositories import NotificationRepository
from src.shared.infrastructure.db.session import get_db
from src.shared.security.auth_context import AuthContext, get_auth_context

router = APIRouter()


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    ctx: AuthContext = Depends(get_auth_context),
    repo: NotificationRepository = Depends(get_notification_repo),
):
    return await repo.list_for_user(ctx.company_id, ctx.user_id, unread_only=unread_only)


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
async def unread_count(
    ctx: AuthContext = Depends(get_auth_context),
    repo: NotificationRepository = Depends(get_notification_repo),
):
    return UnreadCountOut(count=await repo.count_unread(ctx.company_id, ctx.user_id))


@router.post("/notifications/{notification_id}:read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    repo: NotificationRepository = Depends(get_notification_repo),
):
    notification = await repo.get_by_id(notification_id)
    if (
        notification is None
        or notification.company_id != ctx.company_id
        or notification.recipient_user_id != ctx.user_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    await repo.mark_read(notification)
    await db.commit()
    return notification


@router.post("/notifications:read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
    repo: NotificationRepository = Depends(get_notification_repo),
):
    await repo.mark_all_read(ctx.company_id, ctx.user_id)
    await db.commit()
