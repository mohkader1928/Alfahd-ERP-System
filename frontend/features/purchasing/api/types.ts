export interface PurchaseOrderLineIn {
  product_id: string;
  qty: string;
  unit_price: string;
  tax_rate_id: string;
}

export interface PurchaseOrder {
  id: string;
  company_id: string;
  partner_id: string;
  number: string;
  status: "draft" | "pending_approval" | "confirmed" | "partially_received" | "done" | "closed" | "cancelled";
  order_date: string;
  total_amount: string;
  created_by_user_id: string | null;
  approval_status: "not_required" | "pending" | "approved" | "rejected";
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
}

export interface PurchaseOrderLine {
  id: string;
  product_id: string;
  qty: string;
  unit_price: string;
  qty_received: string;
  qty_billed: string;
  short_closed: boolean;
}

export interface PurchaseOrderDetail {
  order: PurchaseOrder;
  lines: PurchaseOrderLine[];
}

export interface GoodsReceipt {
  id: string;
  purchase_order_id: string;
  warehouse_id: string;
  number: string;
  status: string;
  receipt_date: string;
}

export interface VendorBill {
  id: string;
  company_id: string;
  partner_id: string;
  purchase_order_id: string | null;
  number: string;
  vendor_reference: string | null;
  status: string;
  bill_date: string;
  due_date: string | null;
  subtotal_amount: string;
  tax_amount: string;
  total_amount: string;
  mismatch_reasons: string | null;
  bill_type: "standard" | "debit_note";
  original_bill_id: string | null;
  journal_entry_id: string | null;
}

export interface VendorBillLine {
  id: string;
  product_id: string;
  purchase_order_line_id: string | null;
  qty: string;
  unit_price: string;
  tax_rate_percent: string;
  line_total: string;
  tax_amount: string;
}

export interface VendorBillDetail {
  bill: VendorBill;
  lines: VendorBillLine[];
}
