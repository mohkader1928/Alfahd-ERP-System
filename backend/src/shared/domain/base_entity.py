"""Common envelope shared by every domain entity, per Phase 7 §1.1 / FR-CORE-020.

Pure Python — no ORM/framework imports, per the Clean Architecture dependency
rule in Phase 8 §2 (domain must not depend on infrastructure).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class TenantScopedEntity:
    id: UUID
    tenant_id: UUID
    company_id: UUID
    branch_id: UUID | None = None
    created_by: UUID | None = None
    updated_by: UUID | None = None
    deleted_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    version: int = field(default=1)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class DomainError(Exception):
    """Base class for business-rule violations raised from the domain layer."""


class OptimisticLockError(DomainError):
    """Raised when a write targets a stale `version` (Phase 7 §1.5)."""
