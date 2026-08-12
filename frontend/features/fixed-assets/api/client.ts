import { apiClient } from "@/lib/api-client";
import type {
  AssetCard,
  DepreciationEntry,
  DepreciationSchedule,
  DisposeAssetInput,
  FixedAsset,
  FixedAssetCategory,
  FixedAssetCategoryInput,
  FixedAssetCreateInput,
  Reconciliation,
  RunDepreciationResult,
} from "./types";

const BASE = "/api/v1/fixed-assets";

export const fixedAssetsApi = {
  listAssets: (companyId: string, filters?: { categoryId?: string; status?: "active" | "disposed" }) => {
    const params = new URLSearchParams();
    if (filters?.categoryId) params.set("category_id", filters.categoryId);
    if (filters?.status) params.set("status_filter", filters.status);
    const qs = params.toString();
    return apiClient.get<FixedAsset[]>(`${BASE}${qs ? `?${qs}` : ""}`, { companyId });
  },

  getAsset: (companyId: string, id: string) => apiClient.get<FixedAsset>(`${BASE}/${id}`, { companyId }),

  listDepreciationEntries: (companyId: string, id: string) =>
    apiClient.get<DepreciationEntry[]>(`${BASE}/${id}/depreciation-entries`, { companyId }),

  createAsset: (companyId: string, branchId: string, payload: FixedAssetCreateInput) =>
    apiClient.post<FixedAsset>(`${BASE}`, payload, { companyId, branchId }),

  runDepreciation: (companyId: string, branchId: string, periodMonth: string, categoryId?: string | null) =>
    apiClient.post<RunDepreciationResult>(
      `${BASE}:run-depreciation`,
      { period_month: periodMonth, category_id: categoryId || null },
      { companyId, branchId }
    ),

  disposeAsset: (companyId: string, branchId: string, id: string, payload: DisposeAssetInput) =>
    apiClient.post<FixedAsset>(`${BASE}/${id}:dispose`, payload, { companyId, branchId }),

  getAssetCard: (companyId: string, id: string, dateFrom: string, dateTo: string) =>
    apiClient.get<AssetCard>(`${BASE}/${id}/card?date_from=${dateFrom}&date_to=${dateTo}`, { companyId }),

  getReconciliation: (companyId: string, asOfDate: string) =>
    apiClient.get<Reconciliation>(`${BASE}/reconciliation?as_of_date=${asOfDate}`, { companyId }),

  getDepreciationSchedule: (companyId: string, dateFrom: string, dateTo: string, categoryId?: string) => {
    const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
    if (categoryId) params.set("category_id", categoryId);
    return apiClient.get<DepreciationSchedule>(`${BASE}/depreciation-schedule?${params.toString()}`, { companyId });
  },

  listCategories: (companyId: string) => apiClient.get<FixedAssetCategory[]>(`${BASE}/categories`, { companyId }),

  createCategory: (companyId: string, payload: FixedAssetCategoryInput) =>
    apiClient.post<FixedAssetCategory>(`${BASE}/categories`, payload, { companyId }),

  updateCategory: (companyId: string, id: string, payload: FixedAssetCategoryInput) =>
    apiClient.patch<FixedAssetCategory>(`${BASE}/categories/${id}`, payload, { companyId }),

  deleteCategory: (companyId: string, id: string) =>
    apiClient.delete<void>(`${BASE}/categories/${id}`, { companyId }),
};
