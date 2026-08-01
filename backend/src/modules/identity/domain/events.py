from dataclasses import dataclass
from uuid import UUID

from src.shared.infrastructure.messaging.event_bus import DomainEvent


@dataclass(frozen=True)
class UserLoggedIn(DomainEvent):
    user_id: UUID
    tenant_id: UUID


@dataclass(frozen=True)
class RoleAssigned(DomainEvent):
    user_id: UUID
    role_id: UUID
    company_id: UUID


@dataclass(frozen=True)
class CompanyRegistered(DomainEvent):
    """Published after UC-CORE-02. Accounting subscribes to this (Phase 8 §3:
    Accounting depends on Identity, never the reverse) to seed the company's
    default Chart of Accounts/journals/tax rates without Identity importing
    anything from the Accounting module.
    """

    tenant_id: UUID
    company_id: UUID
    valuation_method: str
