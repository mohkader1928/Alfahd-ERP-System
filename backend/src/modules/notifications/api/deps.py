from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.infrastructure.repositories import NotificationRepository
from src.shared.infrastructure.db.session import get_db


def get_notification_repo(db: AsyncSession = Depends(get_db)) -> NotificationRepository:
    return NotificationRepository(db)
