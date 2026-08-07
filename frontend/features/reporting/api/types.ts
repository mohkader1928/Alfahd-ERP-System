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

// ── Global Search ─────────────────────────────────────────────────────────────

export interface SearchResultRow {
  type: string;
  id: string;
  label: string;
  sublabel: string | null;
}
