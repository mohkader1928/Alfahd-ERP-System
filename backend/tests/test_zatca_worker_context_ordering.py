"""Phase 17C-RLS: regression test for the ZATCA worker's RLS-context ordering bug.

Before this fix, `_report_invoice_async` looked up the invoice with
`invoice_repo.get_by_id()` *before* calling `set_company_context()`. That
was invisible while the API/worker connected as the `erp` superuser
(`rolbypassrls=true` bypasses RLS unconditionally regardless of context),
but once the runtime role became `erp_app` (Phase 17C-RLS, no bypass), the
lookup ran under the `company_isolation` policy's default-deny with no
context set — silently returning no rows every time, so the invoice was
never marked as reported to ZATCA.

This test calls the real worker entry point (`_run_with_fresh_pool`, the
same function `report_invoice_task` calls) directly, twice, against one
real pending ZATCA submission created through the full HTTP bootstrap
flow:

  1. First with `company_id=None` — the pre-fix call shape — proving it
     fails closed: no exception, but the submission is left exactly as
     `pending_submission`, i.e. never actually reported. This reproduces
     the bug, it doesn't simulate it.
  2. Then with the real `company_id` — the fixed call shape used by both
     `.delay()` sites in `sales/api/routes.py` — proving the same
     submission is now processed successfully.

Runs against the real dockerized Postgres via the real `erp_app` runtime
role, same as every other test in this suite.

`report_invoice_task.delay(...)` is patched to a no-op during bootstrap:
the real Celery `worker` container is also up and consuming the same Redis
broker in this environment, so the genuine enqueue from
`POST .../orders/{id}:invoice` would otherwise race an actual worker
process against this test's own direct, deliberately-sequenced calls to
`_run_with_fresh_pool` below — non-deterministically reporting the invoice
before the "old call shape" assertion ever runs. Nothing about the
production `.delay()` call itself is touched; only this test's bootstrap
helper avoids triggering it.
"""

import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.api.main import app
from src.shared.infrastructure.db.session import engine
from src.workers.tasks.zatca_tasks import _run_with_fresh_pool
from tests.conftest import unique_email, unique_vat

TAX_RATE_PLACEHOLDER = "00000000-0000-0000-0000-000000000001"


async def _bootstrap_pending_zatca_invoice(client: AsyncClient) -> tuple[str, str, str]:
    """Runs the real quotation -> order -> invoice flow far enough to
    produce one real `pending_submission` ZATCA row. Returns (invoice_id,
    company_id, tenant_id)."""
    payload = {
        "tenant_legal_name": "ZatcaOrdering Holding",
        "company_legal_name": "ZatcaOrdering Trading Co.",
        "company_legal_name_ar": "ZatcaOrdering Trading Arabic",
        "vat_number": unique_vat(),
        "base_currency_code": "SAR",
        "valuation_method": "average",
        "admin_email": unique_email(),
        "admin_full_name": "ZatcaOrdering Admin",
        "admin_password": "Str0ng!Passw0rd",
    }
    boot_resp = await client.post("/api/v1/identity/bootstrap", json=payload)
    assert boot_resp.status_code == 201
    body = boot_resp.json()
    tenant_id, company_id, branch_id = body["tenant_id"], body["company_id"], body["branch_id"]

    login_resp = await client.post(
        "/api/v1/identity/auth/login",
        json={"email": payload["admin_email"], "password": payload["admin_password"]},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Company-Id": company_id, "X-Branch-Id": branch_id}

    # No vat_number: sales/application/services.py derives invoice_type =
    # "simplified" for a VAT-less partner, which uses submission_mode
    # "reporting" (async, via report_invoice_task) rather than "clearance"
    # (synchronous, resolved during issue_invoice_from_order itself) — the
    # async path is the one this test's ordering fix actually applies to.
    partner_resp = await client.post(
        "/api/v1/identity/partners",
        headers=headers,
        json={"name": "ZatcaOrdering Partner", "is_customer": True},
    )
    partner_id = partner_resp.json()["id"]

    product_resp = await client.post(
        "/api/v1/identity/products",
        headers=headers,
        json={"sku": f"SKU-{uuid.uuid4().hex[:8]}", "name": "ZatcaOrdering Product", "sales_price": "100.00"},
    )
    product_id = product_resp.json()["id"]

    wh_resp = await client.post(
        "/api/v1/inventory/warehouses", headers=headers, json={"name": "ZatcaOrdering Warehouse", "is_default": True}
    )
    location_id = wh_resp.json()["default_location"]["id"]

    await client.post(
        "/api/v1/inventory/stock/receive",
        headers=headers,
        json={"product_id": product_id, "location_id": location_id, "qty": "10", "unit_cost": "10.00"},
    )

    quote_resp = await client.post(
        "/api/v1/sales/quotations",
        headers=headers,
        json={
            "partner_id": partner_id,
            "quote_date": "2026-06-01",
            "lines": [{"product_id": product_id, "qty": "1", "unit_price": "100.00", "tax_rate_id": TAX_RATE_PLACEHOLDER}],
        },
    )
    quotation_id = quote_resp.json()["id"]
    order_resp = await client.post(f"/api/v1/sales/quotations/{quotation_id}:confirm", headers=headers)
    order_id = order_resp.json()["id"]

    # See module docstring: a real Celery worker is also consuming this
    # queue in this environment, so the genuine enqueue is suppressed here
    # — this test drives _run_with_fresh_pool directly and deterministically.
    with patch("src.workers.tasks.zatca_tasks.report_invoice_task.delay"):
        invoice_resp = await client.post(f"/api/v1/sales/orders/{order_id}:invoice", headers=headers)
    body = invoice_resp.json()
    invoice_id = body["invoice"]["id"]
    assert body["zatca_submission"]["status"] == "pending_submission"

    return invoice_id, company_id, tenant_id


async def _submission_status(invoice_id: str, company_id: str) -> str:
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(f"SET LOCAL app.current_company_id = '{company_id}'"))
            return (
                await conn.execute(
                    text("SELECT status FROM zatca_submission WHERE sales_invoice_id = :id"), {"id": invoice_id}
                )
            ).scalar_one()
        finally:
            await trans.rollback()


@pytest.mark.asyncio
async def test_old_call_shape_without_company_id_leaves_submission_unreported():
    """Reproduces the pre-fix bug: calling the worker the old way (no
    company_id, context set only after the now-empty lookup) never reports
    the invoice — the submission is left stuck at pending_submission."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invoice_id, company_id, _tenant_id = await _bootstrap_pending_zatca_invoice(client)

    await _run_with_fresh_pool(invoice_id, None, None)

    assert await _submission_status(invoice_id, company_id) == "pending_submission"


@pytest.mark.asyncio
async def test_fixed_call_shape_with_company_id_reports_successfully():
    """The fixed call shape (context set from the enqueue-time company_id
    and tenant_id, before the first query) — the same signature both
    `.delay()` sites in sales/api/routes.py now use — actually reports the
    invoice."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invoice_id, company_id, tenant_id = await _bootstrap_pending_zatca_invoice(client)

    await _run_with_fresh_pool(invoice_id, company_id, tenant_id)

    assert await _submission_status(invoice_id, company_id) != "pending_submission"
