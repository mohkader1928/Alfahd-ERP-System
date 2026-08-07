import uuid
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.infrastructure.models import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def build(
        self,
        *,
        company_id: UUID,
        recipient_user_id: UUID,
        type: str,
        title: str,
        body: str,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        link: str | None = None,
    ) -> Notification:
        return Notification(
            id=uuid.uuid4(),
            company_id=company_id,
            recipient_user_id=recipient_user_id,
            type=type,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            link=link,
        )

    async def add_many(self, notifications: list[Notification]) -> None:
        if not notifications:
            return
        self.session.add_all(notifications)
        await self.session.flush()

    async def list_for_user(
        self, company_id: UUID, user_id: UUID, *, unread_only: bool = False, limit: int = 30
    ) -> list[Notification]:
        query = select(Notification).where(
            Notification.company_id == company_id, Notification.recipient_user_id == user_id
        )
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
        result = await self.session.execute(query.order_by(Notification.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def count_unread(self, company_id: UUID, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).where(
                Notification.company_id == company_id,
                Notification.recipient_user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        return result.scalar_one()

    async def get_by_id(self, notification_id: UUID) -> Notification | None:
        result = await self.session.execute(select(Notification).where(Notification.id == notification_id))
        return result.scalar_one_or_none()

    async def mark_read(self, notification: Notification) -> None:
        notification.is_read = True
        await self.session.flush()

    async def mark_all_read(self, company_id: UUID, user_id: UUID) -> None:
        await self.session.execute(
            update(Notification)
            .where(
                Notification.company_id == company_id,
                Notification.recipient_user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
        )
        await self.session.flush()
