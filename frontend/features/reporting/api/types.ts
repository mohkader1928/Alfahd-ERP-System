export interface DashboardSummary {
  period_start: string;
  period_end: string;
  period_sales_total: string;
  period_purchases_total: string;
  receivables_balance: string;
  payables_balance: string;
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
