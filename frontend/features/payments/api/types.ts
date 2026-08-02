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
