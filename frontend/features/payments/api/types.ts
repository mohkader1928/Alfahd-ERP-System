export type PaymentType = "customer" | "vendor";

export interface PaymentAllocationIn {
  sales_invoice_id?: string | null;
  vendor_bill_id?: string | null;
  amount: string;
}

export interface PaymentAllocation {
  id: string;
  sales_invoice_id: string | null;
  vendor_bill_id: string | null;
  amount: string;
}

export interface Payment {
  id: string;
  company_id: string;
  partner_id: string;
  payment_type: PaymentType;
  number: string;
  payment_date: string;
  amount: string;
  currency_code: string;
  account_id: string;
  reference: string | null;
  journal_entry_id: string | null;
}

export interface PaymentDetail {
  payment: Payment;
  allocations: PaymentAllocation[];
}

export interface DocumentBalance {
  total_amount: string;
  amount_paid: string;
  balance_due: string;
  payment_status: "unpaid" | "partially_paid" | "paid";
}

export interface PaymentCreateInput {
  partner_id: string;
  payment_type: PaymentType;
  payment_date: string;
  amount: string;
  account_id: string;
  reference?: string;
  allocations: PaymentAllocationIn[];
}

export interface SubledgerLine {
  date: string;
  movement_type: "invoice" | "credit_note" | "bill" | "debit_note" | "payment";
  document_type: "sales_invoice" | "vendor_bill" | "payment";
  document_id: string;
  reference: string;
  debit: string;
  credit: string;
  running_balance: string;
}

export interface Subledger {
  partner_id: string;
  partner_name: string;
  date_from: string;
  date_to: string;
  opening_balance: string;
  lines: SubledgerLine[];
  closing_balance: string;
}

export interface AgingRow {
  partner_id: string | null;
  partner_name: string;
  document_id: string;
  number: string;
  due_date: string;
  balance_due: string;
  days_overdue: number;
  bucket: "current" | "1_30" | "31_60" | "61_90" | "over_90";
}

export interface AgingReport {
  as_of_date: string;
  rows: AgingRow[];
}
