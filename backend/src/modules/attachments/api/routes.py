"""FastAPI routes for Attachments (Professional Workspace Layer) — one
generic upload/list/download/delete surface reused by every document type
(sales invoices, purchase orders, vendor bills, journal entries, ...) via
`entity_type`/`entity_id`, the same polymorphic-association convention
`source_table`/`source_id` already use elsewhere in this codebase."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.attachments.api.deps import get_attachment_repo, require_permission
from src.modules.attachments.api.schemas import AttachmentOut
from src.modules.attachments.infrastructure.models import Attachment
from src.modules.attachments.infrastructure.repositories import AttachmentRepository
from src.modules.identity.api.deps import get_user_repo
from src.modules.identity.infrastructure.repositories import UserRepository
from src.shared.infrastructure.db.session import get_db
from src.shared.media.storage import (
    InvalidAttachmentError,
    attachment_file_path,
    delete_attachment_file,
    save_attachment_file,
)
from src.shared.security.auth_context import AuthContext

router = APIRouter()


def _to_out(attachment: Attachment, uploaded_by_name: str) -> AttachmentOut:
    return AttachmentOut(
        id=attachment.id,
        entity_type=attachment.entity_type,
        entity_id=attachment.entity_id,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        file_size=attachment.file_size,
        uploaded_by=attachment.uploaded_by,
        uploaded_by_name=uploaded_by_name,
        uploaded_at=attachment.uploaded_at,
    )


@router.get("/attachments", response_model=list[AttachmentOut])
async def list_attachments(
    entity_type: str,
    entity_id: UUID,
    ctx: AuthContext = Depends(require_permission("attachment.view")),
    repo: AttachmentRepository = Depends(get_attachment_repo),
):
    rows = await repo.list_by_entity(ctx.company_id, entity_type, entity_id)
    return [_to_out(row["attachment"], row["uploaded_by_name"]) for row in rows]


@router.post("/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    entity_type: str,
    entity_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("attachment.manage")),
    repo: AttachmentRepository = Depends(get_attachment_repo),
    user_repo: UserRepository = Depends(get_user_repo),
):
    try:
        relative_path, size = await save_attachment_file(file, company_id=str(ctx.company_id))
    except InvalidAttachmentError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    attachment = Attachment(
        company_id=ctx.company_id,
        entity_type=entity_type,
        entity_id=entity_id,
        file_path=relative_path,
        original_filename=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream",
        file_size=size,
        uploaded_by=ctx.user_id,
    )
    await repo.add(attachment)
    uploader = await user_repo.get_by_id(ctx.user_id)
    await db.commit()
    return _to_out(attachment, uploader.full_name if uploader else "")


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: UUID,
    ctx: AuthContext = Depends(require_permission("attachment.view")),
    repo: AttachmentRepository = Depends(get_attachment_repo),
):
    attachment = await repo.get_by_id(attachment_id)
    if attachment is None or attachment.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")

    path = attachment_file_path(attachment.file_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment file missing")

    return FileResponse(
        path,
        media_type=attachment.content_type,
        filename=attachment.original_filename,
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(require_permission("attachment.manage")),
    repo: AttachmentRepository = Depends(get_attachment_repo),
):
    attachment = await repo.get_by_id(attachment_id)
    if attachment is None or attachment.company_id != ctx.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")

    file_path = attachment.file_path
    await repo.delete(attachment)
    await db.commit()
    delete_attachment_file(file_path)
