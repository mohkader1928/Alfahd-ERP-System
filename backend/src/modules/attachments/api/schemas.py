from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AttachmentOut(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    original_filename: str
    content_type: str
    file_size: int
    uploaded_by: UUID
    uploaded_by_name: str
    uploaded_at: datetime
