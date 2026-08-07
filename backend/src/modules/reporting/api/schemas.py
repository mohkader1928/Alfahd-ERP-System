from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class DashboardSummaryOut(BaseModel):
    period_start: date
    period_end: date
    period_sales_total: Decimal
    period_purchases_total: Decimal
    receivables_balance: Decimal
    payables_balance: Decimal


# ── Sales Reports ──────────────────────────────────────────────────────────────

class SalesByCustomerRow(BaseModel):
    partner_id: UUID
    partner_name: str
    invoice_count: int
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal


class SalesByProductRow(BaseModel):
    product_id: UUID
    product_name: str
    product_code: str
    qty_sold: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal


class SalesByPeriodRow(BaseModel):
    period_label: str   # e.g. "2025-01", "2025-Q1"
    period_start: date
    invoice_count: int
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal


class SearchResultRow(BaseModel):
    type: str
    id: UUID
    label: str
    sublabel: str | None
