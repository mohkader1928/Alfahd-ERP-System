export interface SalesTrendPoint {
  period_label: string;
  total: string;
}

export interface RecentActivityItem {
  entity_type: string;
  entity_id: string;
  label: string;
  date: string;
  amount: string;
}

export interface DashboardSummary {
  period_start: string;
  period_end: string;
  period_sales_total: string;
  period_purchases_total: string;
  receivables_balance: string;
  payables_balance: string;
  cash_balance: string;
  sales_trend: SalesTrendPoint[];
  pending_approvals_count: number;
  recent_activity: RecentActivityItem[];
}

// ── Sales Reports ──────────────────────────────────────────────────────────────

export interface SalesByCustomerRow {
  partner_id: string;
  partner_name: string;
  invoice_count: number;
  subtotal: string;
  tax_amount: string;
  total: string;
  payments_received: string;
  balance: string;
}

export interface SalesByProductRow {
  product_id: string;
  product_name: string;
  product_code: string;
  qty_sold: string;
  subtotal: string;
  tax_amount: string;
  total: string;
}

export interface SalesByPeriodRow {
  period_label: string;
  period_start: string;
  invoice_count: number;
  subtotal: string;
  tax_amount: string;
  total: string;
}

// ── Purchasing Reports ────────────────────────────────────────────────────────

export interface PurchaseByVendorRow {
  partner_id: string;
  partner_name: string;
  bill_count: number;
  subtotal: string;
  tax_amount: string;
  total: string;
  adjustments: string;
  net_total: string;
  payments_made: string;
  balance: string;
}

// ── Inventory Valuation ──────────────────────────────────────────────────────

export interface InventoryValuationRow {
  product_id: string;
  product_code: string;
  product_name: string;
  warehouse_id: string;
  warehouse_name: string;
  qty_on_hand: string;
  unit_cost: string;
  total_value: string;
}

export interface InventoryReconciliation {
  gl_balance: string;
  valuation_total: string;
  difference: string;
  tolerance: string;
  matched: boolean;
}

// ── VAT / Tax Summary ────────────────────────────────────────────────────────

export interface VatSummary {
  date_from: string;
  date_to: string;
  sales_subtotal: string;
  output_vat: string;
  sales_total: string;
  purchases_subtotal: string;
  input_vat: string;
  purchases_total: string;
  net_vat_payable: string;
}

export interface VatDetailRow {
  document_date: string;
  movement_type: "invoice" | "credit_note" | "bill";
  direction: "output" | "input";
  document_id: string;
  number: string;
  partner_name: string;
  subtotal_amount: string;
  vat_amount: string;
  total_amount: string;
}

// ── Global Search ─────────────────────────────────────────────────────────────

export interface SearchResultRow {
  type: string;
  id: string;
  label: string;
  sublabel: string | null;
}
