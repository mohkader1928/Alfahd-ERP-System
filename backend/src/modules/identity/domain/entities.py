"""Pure domain entities for the Identity module (Phase 8 §2 — no ORM/HTTP imports).

These carry business rules only. Persistence shape lives in
infrastructure/models.py; API shape lives in api/schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.shared.domain.base_entity import DomainError


class InactiveUserError(DomainError):
    pass


@dataclass
class Company:
    id: UUID
    tenant_id: UUID
    legal_name: str
    legal_name_ar: str
    vat_number: str
    base_currency_id: UUID
    valuation_method: str  # 'fifo' | 'average', per Phase 7 §2
    zatca_environment: str = "sandbox"
    cr_number: str | None = None
    created_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        if len(self.vat_number) != 15 or not self.vat_number.isdigit():
            raise DomainError("Saudi VAT number must be exactly 15 digits")
        if self.valuation_method not in ("fifo", "average"):
            raise DomainError("valuation_method must be 'fifo' or 'average'")


@dataclass
class Branch:
    id: UUID
    tenant_id: UUID
    company_id: UUID
    name: str
    name_ar: str
    is_main: bool = False


@dataclass
class User:
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    password_hash: str
    is_active: bool = True
    is_2fa_enabled: bool = False
    totp_secret: str | None = None
    preferred_locale: str = "ar"
    preferred_calendar: str = "gregorian"

    def assert_can_login(self) -> None:
        if not self.is_active:
            raise InactiveUserError("This user account has been deactivated")


@dataclass
class Role:
    id: UUID
    company_id: UUID
    name: str
    is_system: bool = False
    permission_codes: list[str] = field(default_factory=list)

    def grants(self, permission_code: str) -> bool:
        return permission_code in self.permission_codes
