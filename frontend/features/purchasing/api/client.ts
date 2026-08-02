import { apiClient } from "@/lib/api-client";
import type {
  GoodsReceipt,
  PurchaseOrder,
  PurchaseOrderDetail,
  PurchaseOrderLineIn,
  VendorBill,
} from "./types";

const BASE = "/api/v1/purchasing";

export const purchasingApi = {
  listOrders: (companyId: string) => apiClient.get<PurchaseOrder[]>(`${BASE}/orders`, { companyId }),

  createOrder: (
    companyId: string,
    branchId: string,
    payload: { partner_id: string; order_date: string; lines: PurchaseOrderLineIn[] }
  ) => apiClient.post<PurchaseOrder>(`${BASE}/orders`, payload, { companyId, branchId }),

  getOrder: (companyId: string, id: string) =>
    apiClient.get<PurchaseOrderDetail>(`${BASE}/orders/${id}`, { companyId }),

  confirmOrder: (companyId: string, id: string) =>
    apiClient.post<PurchaseOrder>(`${BASE}/orders/${id}:confirm`, undefined, { companyId }),

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

  listVendorBills: (companyId: string, partnerId?: string) =>
    apiClient.get<VendorBill[]>(`${BASE}/vendor-bills${partnerId ? `?partner_id=${partnerId}` : ""}`, { companyId }),

  approveVendorBill: (companyId: string, id: string) =>
    apiClient.post<VendorBill>(`${BASE}/vendor-bills/${id}:approve`, undefined, { companyId }),
};
