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
}

export interface SalesOrder {
  id: string;
  company_id: string;
  partner_id: string;
  quotation_id: string | null;
  number: string;
  status: "draft" | "confirmed" | "done" | "cancelled";
  order_date: string;
  total_amount: string;
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
  subtotal_amount: string;
  tax_amount: string;
  total_amount: string;
}

export interface InvoiceIssueResponse {
  invoice: SalesInvoice;
  zatca_submission: ZatcaSubmission;
}
