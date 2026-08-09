import { apiClient } from "@/lib/api-client";
import type {
  AssetCard,
  DepreciationEntry,
  DisposeAssetInput,
  FixedAsset,
  FixedAssetCreateInput,
  Reconciliation,
  RunDepreciationResult,
} from "./types";

const BASE = "/api/v1/fixed-assets";

export const fixedAssetsApi = {
  listAssets: (companyId: string) => apiClient.get<FixedAsset[]>(`${BASE}`, { companyId }),

  getAsset: (companyId: string, id: string) => apiClient.get<FixedAsset>(`${BASE}/${id}`, { companyId }),

  listDepreciationEntries: (companyId: string, id: string) =>
    apiClient.get<DepreciationEntry[]>(`${BASE}/${id}/depreciation-entries`, { companyId }),

  createAsset: (companyId: string, branchId: string, payload: FixedAssetCreateInput) =>
    apiClient.post<FixedAsset>(`${BASE}`, payload, { companyId, branchId }),

  runDepreciation: (companyId: string, branchId: string, periodMonth: string) =>
    apiClient.post<RunDepreciationResult>(`${BASE}:run-depreciation`, { period_month: periodMonth }, { companyId, branchId }),

  disposeAsset: (companyId: string, branchId: string, id: string, payload: DisposeAssetInput) =>
    apiClient.post<FixedAsset>(`${BASE}/${id}:dispose`, payload, { companyId, branchId }),

  getAssetCard: (companyId: string, id: string, dateFrom: string, dateTo: string) =>
    apiClient.get<AssetCard>(`${BASE}/${id}/card?date_from=${dateFrom}&date_to=${dateTo}`, { companyId }),

  getReconciliation: (companyId: string, asOfDate: string) =>
    apiClient.get<Reconciliation>(`${BASE}/reconciliation?as_of_date=${asOfDate}`, { companyId }),
};
