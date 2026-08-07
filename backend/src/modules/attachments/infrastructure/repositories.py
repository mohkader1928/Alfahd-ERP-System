from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.attachments.infrastructure.models import Attachment
from src.modules.identity.infrastructure.models import AppUser


class AttachmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, attachment: Attachment) -> Attachment:
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def get_by_id(self, attachment_id: UUID) -> Attachment | None:
        result = await self.session.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def list_by_entity(self, company_id: UUID, entity_type: str, entity_id: UUID) -> list[dict]:
        result = await self.session.execute(
            select(Attachment, AppUser.full_name)
            .join(AppUser, AppUser.id == Attachment.uploaded_by)
            .where(
                Attachment.company_id == company_id,
                Attachment.entity_type == entity_type,
                Attachment.entity_id == entity_id,
            )
            .order_by(Attachment.uploaded_at.desc())
        )
        return [{"attachment": row[0], "uploaded_by_name": row[1]} for row in result.all()]

    async def delete(self, attachment: Attachment) -> None:
        await self.session.delete(attachment)
        await self.session.flush()
