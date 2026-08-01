import { apiClient } from "@/lib/api-client";
import type { DashboardSummary } from "./types";

const BASE = "/api/v1/reporting";

export const reportingApi = {
  getDashboard: (companyId: string, periodStart: string, periodEnd: string) =>
    apiClient.get<DashboardSummary>(
      `${BASE}/dashboard?period_start=${periodStart}&period_end=${periodEnd}`,
      { companyId }
    ),
};
