"""Phase 17A: shared report-filter contract for future report endpoints
(docs/17-erp-standardization-master-blueprint.md §15/§20 — General Ledger,
aging, P&L, sales/purchase analysis, etc., none of which are built yet).

Not consumed by any existing endpoint in this phase — Reporting today has
exactly 3 endpoints (dashboard, 2 CSV exports) and none of them take a
filter shaped like this. This exists so Phase 17B+ reports share one
filter contract instead of each hand-rolling its own query params, per
the "one filter system → all reports" principle in the Phase 17A brief.

Every field is optional: a given report only reads the subset that makes
sense for it (e.g. a General Ledger reads `account_id`+dates; a Sales
Register reads `customer_id`+`product_id`+dates) — callers are expected to
validate the specific combination they require, this type does not.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class ReportFilter:
    company_id: UUID
    branch_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    customer_id: UUID | None = None
    vendor_id: UUID | None = None
    product_id: UUID | None = None
    category_id: UUID | None = None
    warehouse_id: UUID | None = None
    location_id: UUID | None = None
    account_id: UUID | None = None
    document_status: str | None = None
    group_by: str | None = None
