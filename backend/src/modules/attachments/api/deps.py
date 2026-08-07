from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.attachments.infrastructure.repositories import AttachmentRepository
from src.modules.identity.api.deps import require_permission  # noqa: F401 (re-exported for routes)
from src.shared.infrastructure.db.session import get_db


def get_attachment_repo(db: AsyncSession = Depends(get_db)) -> AttachmentRepository:
    return AttachmentRepository(db)
