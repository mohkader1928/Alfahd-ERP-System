"""Application service for Company Profile (Adaptive ERP Stage 2.1).

Read/create/update only — no sizing, blueprint, or configuration logic
lives here (those are Stage 2.2-2.4, separate services in this same
module per docs/adaptive/06-configuration-engine-architecture.md §6.2).
"""

import uuid
from dataclasses import fields
from typing import Any
from uuid import UUID

from src.modules.company_profile.domain.entities import CompanyProfile as CompanyProfileDomain
from src.modules.company_profile.infrastructure.models import CompanyProfile
from src.modules.company_profile.infrastructure.repositories import CompanyProfileRepository
from src.modules.identity.infrastructure.repositories import AuditLogRepository

# Fields a caller may set — everything on the domain entity except its
# identity columns (id/tenant_id/company_id), which are never client-supplied
# (docs/adaptive/12 Principle 3 — same "company_id is never client-supplied"
# rule already proven by test_insert_isolation_company_id_is_never_client_supplied
# in the Golden Core's own multi-tenancy isolation test suite).
_WRITABLE_FIELDS = tuple(
    f.name for f in fields(CompanyProfileDomain) if f.name not in ("id", "tenant_id", "company_id")
)


class CompanyProfileService:
    def __init__(self, profile_repo: CompanyProfileRepository, audit_repo: AuditLogRepository):
        self.profile_repo = profile_repo
        self.audit_repo = audit_repo

    async def get(self, *, company_id: UUID) -> CompanyProfile | None:
        return await self.profile_repo.get_by_company(company_id)

    async def create(
        self, *, tenant_id: UUID, company_id: UUID, user_id: UUID | None, values: dict[str, Any]
    ) -> CompanyProfile:
        existing = await self.profile_repo.get_by_company(company_id)
        if existing is not None:
            raise ValueError("A company_profile already exists for this company — use update instead")

        # Validate via the domain entity first (raises ValueError on bad
        # input, e.g. a negative count or an unknown approval_rigor_preference)
        # before ever touching the ORM/DB — same "validate in domain, persist
        # in infrastructure" separation the Golden Core's Company entity uses.
        domain_values = {k: v for k, v in values.items() if k in _WRITABLE_FIELDS}
        CompanyProfileDomain(id=uuid.uuid4(), tenant_id=tenant_id, company_id=company_id, **domain_values)

        profile = CompanyProfile(
            tenant_id=tenant_id,
            company_id=company_id,
            created_by=user_id,
            **domain_values,
        )
        profile = await self.profile_repo.add(profile)

        for field_name, new_value in domain_values.items():
            await self.audit_repo.record(
                tenant_id=tenant_id,
                company_id=company_id,
                user_id=user_id,
                target_table="company_profile",
                target_id=profile.id,
                field_name=field_name,
                old_value=None,
                new_value=str(new_value) if new_value is not None else None,
            )
        return profile

    async def update(
        self, *, company_id: UUID, tenant_id: UUID, user_id: UUID | None, values: dict[str, Any]
    ) -> CompanyProfile:
        profile = await self.profile_repo.get_by_company(company_id)
        if profile is None:
            raise LookupError("No company_profile exists for this company yet — create one first")

        domain_values = {k: v for k, v in values.items() if k in _WRITABLE_FIELDS}
        # Merge onto current values so a partial update still validates a
        # complete, consistent entity (e.g. changing only coa_depth_preference
        # still re-checks approval_rigor_preference's current value).
        current = {name: getattr(profile, name) for name in _WRITABLE_FIELDS}
        merged = {**current, **domain_values}
        CompanyProfileDomain(id=profile.id, tenant_id=tenant_id, company_id=company_id, **merged)

        old_values = dict(current)
        for field_name, new_value in domain_values.items():
            setattr(profile, field_name, new_value)
        profile.updated_by = user_id

        for field_name, new_value in domain_values.items():
            old_value = old_values[field_name]
            if old_value != new_value:
                await self.audit_repo.record(
                    tenant_id=tenant_id,
                    company_id=company_id,
                    user_id=user_id,
                    target_table="company_profile",
                    target_id=profile.id,
                    field_name=field_name,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                )
        return profile
