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


class RepresentativePerformanceRow(BaseModel):
    representative_id: UUID | None
    representative_name: str
    is_unattributed: bool
    gross_sales: Decimal
    returns: Decimal
    net_sales: Decimal
    invoice_count: int
    customer_count: int
    average_invoice_value: Decimal
    collections: Decimal
    outstanding_balance: Decimal
    sales_commission: Decimal
    collection_commission: Decimal
    net_commission: Decimal


class DashboardSummaryOut(BaseModel):
    period_start: date
    period_end: date
    period_sales_total: Decimal
    period_purchases_total: Decimal
    receivables_balance: Decimal
    payables_balance: Decimal
    cash_balance: Decimal
    sales_trend: list[SalesTrendPointOut]
    pending_approvals_count: int
    recent_activity: list[RecentActivityItemOut]
    # Commercial Performance Stage 3
    commercial_total_sales: Decimal
    commercial_total_returns: Decimal
    commercial_net_sales: Decimal
    commercial_total_collections: Decimal
    commercial_sales_commission: Decimal
    commercial_collection_commission: Decimal
    commercial_net_commission: Decimal
    commercial_unattributed_sales: Decimal
    representative_performance: list[RepresentativePerformanceRow]
    collections_trend: list[SalesTrendPointOut]


# ── Sales Reports ──────────────────────────────────────────────────────────────

class SalesByCustomerRow(BaseModel):
    partner_id: UUID
    partner_name: str
    invoice_count: int
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    payments_received: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")


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


# ── Purchasing Reports ─────────────────────────────────────────────────────────

class PurchaseByVendorRow(BaseModel):
    partner_id: UUID
    partner_name: str
    bill_count: int
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    adjustments: Decimal = Decimal("0")
    net_total: Decimal = Decimal("0")
    payments_made: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")


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


class VatReconciliationOut(BaseModel):
    date_from: date
    date_to: date
    summary_net_vat_payable: Decimal
    gl_net_vat_payable: Decimal
    difference: Decimal
    tolerance: Decimal
    matched: bool


class VatDetailRowOut(BaseModel):
    document_date: date
    movement_type: str
    direction: str
    document_id: UUID
    number: str
    partner_name: str
    subtotal_amount: Decimal
    vat_amount: Decimal
    total_amount: Decimal


class InventoryValuationRowOut(BaseModel):
    product_id: UUID
    product_code: str
    product_name: str
    warehouse_id: UUID
    warehouse_name: str
    qty_on_hand: Decimal
    unit_cost: Decimal
    total_value: Decimal


# ── Commercial Performance Reports (Stage 3) ─────────────────────────────────

class RepresentativeCustomerRow(BaseModel):
    partner_id: UUID
    partner_name: str
    invoice_count: int
    gross_sales: Decimal
    returns: Decimal
    net_sales: Decimal
    average_invoice_value: Decimal


class RepresentativeSalesLineRow(BaseModel):
    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    customer_name: str
    sales_amount: Decimal
    commission_rate: Decimal | None
    commission_amount: Decimal


class RepresentativeReturnsLineRow(BaseModel):
    credit_note_id: UUID
    credit_note_number: str
    credit_note_date: date
    customer_name: str
    original_invoice_number: str | None
    return_amount: Decimal
    commission_rate: Decimal | None
    commission_amount: Decimal


class RepresentativeCollectionsLineRow(BaseModel):
    payment_id: UUID
    payment_number: str
    payment_date: date
    customer_name: str
    collection_amount: Decimal
    commission_rate: Decimal | None
    commission_amount: Decimal


class RepresentativePerformanceDetailOut(BaseModel):
    summary: RepresentativePerformanceRow | None
    sales_lines: list[RepresentativeSalesLineRow]
    returns_lines: list[RepresentativeReturnsLineRow]
    collections_lines: list[RepresentativeCollectionsLineRow]


class InventoryReconciliationOut(BaseModel):
    gl_balance: Decimal
    valuation_total: Decimal
    difference: Decimal
    tolerance: Decimal
    matched: bool
