from fastapi import FastAPI

from src.modules.accounting.api.routes import router as accounting_router
from src.modules.accounting.application.services import ChartOfAccountsService
from src.modules.accounting.infrastructure.repositories import (
    AccountRepository,
    AccountTypeRepository,
    JournalRepository,
    TaxRepository,
)
from src.modules.identity.domain.events import CompanyRegistered
from src.shared.infrastructure.db.session import AsyncSessionLocal, set_company_context
from src.shared.infrastructure.messaging.event_bus import EventBus


async def _on_company_registered(event: CompanyRegistered) -> None:
    """Seeds the default Saudi Chart of Accounts, journals, and tax rates
    for a newly registered company (Phase 5 business flow precondition for
    M2's Order-to-Cash). Runs in its own session/transaction since domain
    event handlers don't share the publisher's request-scoped session —
    see Phase 8 §7 note on Domain Events.
    """
    async with AsyncSessionLocal() as session:
        await set_company_context(session, event.company_id)
        account_repo = AccountRepository(session)
        account_type_repo = AccountTypeRepository(session)
        journal_repo = JournalRepository(session)
        tax_repo = TaxRepository(session)

        service = ChartOfAccountsService(account_repo, account_type_repo, journal_repo, tax_repo)
        accounts_by_code = await service.seed_default_chart_of_accounts(event.company_id)
        await service.seed_default_journals(event.company_id, accounts_by_code)
        await service.seed_default_tax_rates(event.company_id)

        await session.commit()


def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(accounting_router, prefix="/api/v1/accounting", tags=["accounting"])
    event_bus.subscribe(CompanyRegistered, _on_company_registered)
