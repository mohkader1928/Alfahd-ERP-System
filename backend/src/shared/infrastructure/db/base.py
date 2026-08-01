"""SQLAlchemy declarative base + the common tenant-scoped column envelope.

Every module's ORM model (infrastructure/models.py) mixes in `TenantScopedMixin`
to get the Phase 7 §1.1 envelope without repeating it per table.
"""

import uuid
from datetime import datetime

from sqlalchemy import Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantScopedMixin:
    """Common envelope per FR-CORE-020. Mixed into every tenant-scoped table."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), onupdate=text("now()"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
