"""Resolves the display name for a company on a report header, honoring
the requested export language — same Arabic/English fallback every report
export needs, written once."""

from __future__ import annotations

from uuid import UUID

from src.modules.identity.infrastructure.repositories import CompanyRepository


async def resolve_company_name(company_repo: CompanyRepository, company_id: UUID, lang: str) -> str:
    company = await company_repo.get_by_id(company_id)
    if company is None:
        return ""
    if lang == "ar" and company.legal_name_ar:
        return company.legal_name_ar
    return company.legal_name
