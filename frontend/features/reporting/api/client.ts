import { apiClient } from "@/lib/api-client";
import type {
  DashboardSummary,
  InventoryReconciliation,
  InventoryValuationRow,
  PurchaseByVendorRow,
  SalesByCustomerRow,
  SalesByPeriodRow,
  SalesByProductRow,
  SearchResultRow,
  VatDetailRow,
  VatSummary,
} from "./types";

const BASE = "/api/v1/reporting";

export const reportingApi = {
  getDashboard: (companyId: string, periodStart: string, periodEnd: string) =>
    apiClient.get<DashboardSummary>(
      `${BASE}/dashboard?period_start=${periodStart}&period_end=${periodEnd}`,
      { companyId }
    ),

  // ── Sales Reports ────────────────────────────────────────────────────────────

  salesByCustomer: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<SalesByCustomerRow[]>(
      `${BASE}/sales/by-customer?date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),

  salesByProduct: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<SalesByProductRow[]>(
      `${BASE}/sales/by-product?date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),

  salesByPeriod: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<SalesByPeriodRow[]>(
      `${BASE}/sales/by-period?date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),

  // ── Purchasing Reports ───────────────────────────────────────────────────────

  purchasesBySupplier: (companyId: string, dateFrom: string, dateTo: string, partnerId?: string) =>
    apiClient.get<PurchaseByVendorRow[]>(
      `${BASE}/purchasing/by-supplier?date_from=${dateFrom}&date_to=${dateTo}${partnerId ? `&partner_id=${partnerId}` : ""}`,
      { companyId }
    ),

  search: (companyId: string, q: string) =>
    apiClient.get<SearchResultRow[]>(`${BASE}/search?q=${encodeURIComponent(q)}`, { companyId }),

  // ── VAT / Tax Summary ─────────────────────────────────────────────────────────

  vatSummary: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<VatSummary>(`${BASE}/vat-summary?date_from=${dateFrom}&date_to=${dateTo}`, { companyId }),

  vatDetail: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<VatDetailRow[]>(`${BASE}/vat-detail?date_from=${dateFrom}&date_to=${dateTo}`, { companyId }),

  // ── Inventory Valuation ────────────────────────────────────────────────────────

  inventoryValuation: (companyId: string, warehouseId?: string) =>
    apiClient.get<InventoryValuationRow[]>(
      `${BASE}/inventory-valuation${warehouseId ? `?warehouse_id=${warehouseId}` : ""}`,
      { companyId }
    ),

  inventoryReconciliation: (companyId: string) =>
    apiClient.get<InventoryReconciliation>(`${BASE}/inventory-reconciliation`, { companyId }),

  // ── CSV Exports ──────────────────────────────────────────────────────────────

  exportSalesInvoicesCsv: (companyId: string) => apiClient.getBlob(`${BASE}/export/sales-invoices`, { companyId }),
};
