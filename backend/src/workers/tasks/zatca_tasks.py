"""Celery tasks for asynchronous ZATCA Reporting (FR-ZATCA-007) and its
retry behavior (NFR-AVAIL-003).

Scope note: this implements per-task retry (Celery's own `autoretry_for` /
`max_retries` — handles "the ZATCA call itself failed, try again"). It does
NOT implement the separate cross-tenant "sweep for invoices that never got
enqueued at all" job describable from NFR-AVAIL-003 (e.g. the API process
crashing between `db.commit()` and `.delay()`) — that job needs a
BYPASSRLS-capable worker DB role to safely query across every company's
`pending_submission` rows, which is real infra work deferred as a follow-up
rather than bolted on here.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from src.modules.identity.infrastructure.repositories import CompanyRepository, PartnerRepository
from src.modules.sales.infrastructure.repositories import (
    SalesInvoiceRepository,
    ZatcaSubmissionRepository,
)
from src.modules.zatca.application.zatca_service import PreparedInvoice, ZatcaInvoiceProcessor
from src.modules.zatca.domain.entities import InvoiceData
from src.modules.zatca.infrastructure.gateways.sandbox_gateway import SandboxZatcaGateway
from src.modules.zatca.infrastructure.signing import DevSigningService
from src.shared.infrastructure.db.session import (
    AsyncSessionLocal,
    engine,
    set_company_context,
    set_tenant_context,
)
from src.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(Exception,), max_retries=5, retry_backoff=True, retry_backoff_max=600)
def report_invoice_task(
    self, invoice_id: str, company_id: str | None = None, tenant_id: str | None = None
) -> None:
    asyncio.run(_run_with_fresh_pool(invoice_id, company_id, tenant_id))


async def _run_with_fresh_pool(invoice_id: str, company_id: str | None, tenant_id: str | None = None) -> None:
    # The shared async engine's connection pool is a module-level singleton
    # (fine for the FastAPI app, which keeps one event loop for its whole
    # lifetime). Celery's prefork worker calls `asyncio.run()` per task,
    # creating a NEW event loop each time — a pooled asyncpg connection
    # opened under a previous loop breaks when reused under a new one
    # ("attached to a different loop"). Disposing the pool before each task
    # forces fresh connections bound to *this* task's loop.
    await engine.dispose()
    try:
        await _report_invoice_async(invoice_id, company_id, tenant_id)
    finally:
        await engine.dispose()


async def _report_invoice_async(invoice_id: str, company_id: str | None, tenant_id: str | None = None) -> None:
    async with AsyncSessionLocal() as session:
        invoice_repo = SalesInvoiceRepository(session)
        submission_repo = ZatcaSubmissionRepository(session)

        if company_id is not None:
            # Phase 17C-RLS: company context MUST be set before the first
            # RLS-protected query. The runtime role (erp_app) no longer
            # bypasses RLS, so querying before context is set returns no
            # rows under the company_isolation policy's default-deny —
            # querying afterward, as this used to do, silently produced
            # `invoice is None` on every call once RLS became enforced.
            await set_company_context(session, uuid.UUID(company_id))
        if tenant_id is not None:
            # `company` (queried below) carries tenant_isolation, not
            # company_isolation (Phase 7 §3: identity's root tables use
            # tenant_id, everything downstream uses company_id) — this was
            # a pre-existing gap in this task even before the ordering fix,
            # newly surfaced now that RLS is genuinely enforced.
            await set_tenant_context(session, uuid.UUID(tenant_id))

        invoice = await invoice_repo.get_by_id(uuid.UUID(invoice_id))
        if invoice is None:
            return

        if company_id is None:
            # Backward-compat path for tasks already enqueued (in Redis)
            # under the old two/three-argument signature before this
            # deploy — no company_id was serialized into the task message,
            # so context can't be set before the lookup above. Under RLS
            # enforcement that lookup already failed closed and returned
            # above; this branch only runs when the runtime role still
            # bypasses RLS (an in-place upgrade caught mid-transition),
            # preserving the previous ordering as a safety net rather than
            # crashing. Remove this branch and the optional parameters
            # once the queue is confirmed drained of pre-deploy tasks.
            await set_company_context(session, invoice.company_id)

        submission = await submission_repo.get_by_invoice_id(invoice.id)
        if submission is None or submission.status != "pending_submission":
            return  # already processed, or nothing to report — idempotent no-op

        company_repo = CompanyRepository(session)
        partner_repo = PartnerRepository(session)
        # No backward-compat recovery for a missing tenant_id: unlike
        # company_id, `sales_invoice` carries no tenant_id column to fall
        # back to, so an old-shape task with tenant_id=None simply can't
        # look up the company below (tenant_isolation, not
        # company_isolation) — it fails loudly via the RuntimeError below,
        # which autoretry_for surfaces rather than silently swallowing.
        company = await company_repo.get_by_id(invoice.company_id)
        partner = await partner_repo.get_by_id(invoice.partner_id)
        if company is None or partner is None:
            raise RuntimeError(f"Company/Partner missing for invoice {invoice_id}; cannot report to ZATCA")

        invoice_data = InvoiceData(
            invoice_id=invoice.id,
            invoice_number=invoice.number,
            invoice_type=invoice.invoice_type,
            issue_datetime_iso=invoice.created_at.isoformat(),
            seller_name=company.legal_name,
            seller_vat_number=company.vat_number,
            buyer_name=partner.name,
            buyer_vat_number=partner.vat_number,
            currency_code=invoice.currency_code,
            subtotal_amount=invoice.subtotal_amount,
            tax_amount=invoice.tax_amount,
            total_amount=invoice.total_amount,
            lines=[],  # not needed by the gateway for this stage — see module docstring
        )
        prepared = PreparedInvoice(
            uuid_value=submission.uuid_value,
            icv=submission.icv,
            previous_hash=submission.previous_hash,
            invoice_hash=submission.invoice_hash,
            qr_payload=submission.qr_payload,
            xml_document=submission.xml_document,
        )

        processor = ZatcaInvoiceProcessor(gateway=SandboxZatcaGateway(), signing_service=DevSigningService())
        result = await processor.submit_prepared(invoice_data, prepared, submission_mode="reporting")

        submission.status = result.status
        submission.zatca_response = result.zatca_response
        submission.submitted_at = datetime.now(UTC).replace(tzinfo=None)
        submission.retry_count += 1
        invoice.status = result.status

        await session.commit()
