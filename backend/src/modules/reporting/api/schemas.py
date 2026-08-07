from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class SalesTrendPointOut(BaseModel):
    period_label: str
    total: Decimal


class RecentActivityItemOut(BaseModel):
    entity_type: str
    entity_id: UUID
    label: str
    date: date
    amount: Decimal


class DashboardSummaryOut(BaseModel):
    period_start: date
    period_end: date
    period_sales_total: Decimal
    period_purchases_total: Decimal
    receivables_balance: Decimal
    payables_balance: Decimal
    sales_trend: list[SalesTrendPointOut]
    pending_approvals_count: int
    recent_activity: list[RecentActivityItemOut]


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


class VatSummaryOut(BaseModel):
    date_from: date
    date_to: date
    sales_subtotal: Decimal
    output_vat: Decimal
    sales_total: Decimal
    purchases_subtotal: Decimal
    input_vat: Decimal
    purchases_total: Decimal
    net_vat_payable: Decimal


class InventoryValuationRowOut(BaseModel):
    product_id: UUID
    product_code: str
    product_name: str
    warehouse_id: UUID
    warehouse_name: str
    qty_on_hand: Decimal
    unit_cost: Decimal
    total_value: Decimal
