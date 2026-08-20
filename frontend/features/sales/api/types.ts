export interface QuotationLineIn {
  product_id: string;
  qty: string;
  unit_price: string;
  tax_rate_id: string;
}

export interface Quotation {
  id: string;
  company_id: string;
  partner_id: string;
  number: string;
  status: "draft" | "confirmed" | "done" | "cancelled";
  quote_date: string;
  total_amount: string;
  warehouse_id: string | null;
  cost_center_id: string | null;
  payment_terms: string | null;
  last_emailed_at: string | null;
  last_emailed_to: string | null;
}

export interface QuotationLine {
  id: string;
  product_id: string;
  qty: string;
  unit_price: string;
  tax_rate_id: string;
}

export interface QuotationDetailResponse {
  quotation: Quotation;
  lines: QuotationLine[];
}

export interface SalesOrder {
  id: string;
  company_id: string;
  partner_id: string;
  quotation_id: string | null;
  number: string;
  status: "draft" | "confirmed" | "partially_invoiced" | "done" | "cancelled";
  order_date: string;
  total_amount: string;
  warehouse_id: string | null;
  cost_center_id: string | null;
  cancellation_reason: string | null;
}

export interface SalesOrderLine {
  id: string;
  product_id: string;
  qty: string;
  unit_price: string;
  qty_invoiced: string;
}

export interface SalesOrderDetailResponse {
  order: SalesOrder;
  lines: SalesOrderLine[];
}

export interface SalesOrderLineIn {
  product_id: string;
  qty: string;
  unit_price: string;
  tax_rate_id: string;
}

export interface InvoiceLineQtyIn {
  sales_order_line_id: string;
  qty: string;
}

export interface ZatcaSubmission {
  id: string;
  uuid_value: string;
  icv: number;
  invoice_hash: string;
  qr_payload: string;
  submission_mode: "clearance" | "reporting";
  status: string;
}

export interface SalesInvoice {
  id: string;
  company_id: string;
  partner_id: string;
  sales_order_id: string | null;
  original_invoice_id: string | null;
  invoice_type: "tax" | "simplified" | "credit_note" | "debit_note";
  number: string;
  status: string;
  invoice_date: string;
  subtotal_amount: string;
  tax_amount: string;
  total_amount: string;
  warehouse_id: string | null;
  cost_center_id: string | null;
  journal_entry_id: string | null;
  last_emailed_at: string | null;
  last_emailed_to: string | null;
}

export interface SalesInvoiceLine {
  id: string;
  product_id: string;
  qty: string;
  unit_price: string;
  tax_rate_id: string;
}

export interface InvoiceIssueResponse {
  invoice: SalesInvoice;
  zatca_submission: ZatcaSubmission;
  lines: SalesInvoiceLine[];
}
