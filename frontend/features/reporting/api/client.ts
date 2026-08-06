import { apiClient } from "@/lib/api-client";
import type {
  DashboardSummary,
  SalesByCustomerRow,
  SalesByPeriodRow,
  SalesByProductRow,
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
};
