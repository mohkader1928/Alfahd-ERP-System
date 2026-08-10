import { apiClient } from "@/lib/api-client";
import type { Page } from "@/lib/pagination";
import type {
  GoodsReceipt,
  PurchaseOrder,
  PurchaseOrderDetail,
  PurchaseOrderLineIn,
  VendorBill,
  VendorBillDetail,
} from "./types";

const BASE = "/api/v1/purchasing";

export interface PurchaseOrderListFilters {
  status?: string;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}

export interface VendorBillListFilters {
  partnerId?: string;
  status?: string;
  dateFrom?: string;
  dateTo?: string;
  billType?: string;
  page?: number;
  pageSize?: number;
}

export const purchasingApi = {
  listOrders: (companyId: string, filters: PurchaseOrderListFilters = {}) => {
    const qs = new URLSearchParams();
    if (filters.status) qs.set("status", filters.status);
    if (filters.dateFrom) qs.set("date_from", filters.dateFrom);
    if (filters.dateTo) qs.set("date_to", filters.dateTo);
    qs.set("page", String(filters.page ?? 1));
    qs.set("page_size", String(filters.pageSize ?? 50));
    return apiClient.get<Page<PurchaseOrder>>(`${BASE}/orders?${qs.toString()}`, { companyId });
  },

  createOrder: (
    companyId: string,
    branchId: string,
    payload: { partner_id: string; order_date: string; lines: PurchaseOrderLineIn[] }
  ) => apiClient.post<PurchaseOrder>(`${BASE}/orders`, payload, { companyId, branchId }),

  getOrder: (companyId: string, id: string) =>
    apiClient.get<PurchaseOrderDetail>(`${BASE}/orders/${id}`, { companyId }),

  confirmOrder: (companyId: string, id: string) =>
    apiClient.post<PurchaseOrder>(`${BASE}/orders/${id}:confirm`, undefined, { companyId }),

  approveOrder: (companyId: string, id: string) =>
    apiClient.post<PurchaseOrder>(`${BASE}/orders/${id}:approve`, undefined, { companyId }),

  rejectOrder: (companyId: string, id: string, reason: string) =>
    apiClient.post<PurchaseOrder>(`${BASE}/orders/${id}:reject`, { reason }, { companyId }),

  shortCloseOrder: (companyId: string, id: string, reason: string) =>
    apiClient.post<PurchaseOrder>(`${BASE}/orders/${id}:short-close`, { reason }, { companyId }),

  reopenOrderLine: (companyId: string, orderId: string, lineId: string) =>
    apiClient.post<PurchaseOrder>(`${BASE}/orders/${orderId}/lines/${lineId}:reopen`, undefined, { companyId }),

  recordGoodsReceipt: (
    companyId: string,
    branchId: string,
    orderId: string,
    payload: { lines: { purchase_order_line_id: string; qty: string }[] }
  ) => apiClient.post<GoodsReceipt>(`${BASE}/orders/${orderId}/goods-receipts`, payload, { companyId, branchId }),

  registerVendorBill: (
    companyId: string,
    branchId: string,
    orderId: string,
    payload: { vendor_reference?: string; lines: { purchase_order_line_id: string; qty: string; unit_price: string }[] }
  ) => apiClient.post<VendorBill>(`${BASE}/orders/${orderId}/vendor-bills`, payload, { companyId, branchId }),

  listVendorBills: (companyId: string, filters: VendorBillListFilters = {}) => {
    const qs = new URLSearchParams();
    if (filters.partnerId) qs.set("partner_id", filters.partnerId);
    if (filters.status) qs.set("status", filters.status);
    if (filters.dateFrom) qs.set("date_from", filters.dateFrom);
    if (filters.dateTo) qs.set("date_to", filters.dateTo);
    if (filters.billType) qs.set("bill_type", filters.billType);
    qs.set("page", String(filters.page ?? 1));
    qs.set("page_size", String(filters.pageSize ?? 50));
    return apiClient.get<Page<VendorBill>>(`${BASE}/vendor-bills?${qs.toString()}`, { companyId });
  },

  approveVendorBill: (companyId: string, id: string) =>
    apiClient.post<VendorBill>(`${BASE}/vendor-bills/${id}:approve`, undefined, { companyId }),

  issueDebitNote: (companyId: string, branchId: string, id: string, reason: string, restock = true) =>
    apiClient.post<VendorBill>(`${BASE}/vendor-bills/${id}:debit-note`, { reason, restock }, { companyId, branchId }),

  getVendorBill: (companyId: string, id: string) =>
    apiClient.get<VendorBillDetail>(`${BASE}/vendor-bills/${id}`, { companyId }),
};
