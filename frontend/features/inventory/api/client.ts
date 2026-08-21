import { apiClient } from "@/lib/api-client";
import type {
  CycleCount,
  CycleCountDetail,
  CycleCountLineIn,
  Location,
  LowStockRow,
  ProductCardex,
  StockBalance,
  StockBalanceByProduct,
  StockMove,
  StockQuant,
  Warehouse,
  WarehouseCreateResult,
} from "./types";

const BASE = "/api/v1/inventory";

export const inventoryApi = {
  listWarehouses: (companyId: string) => apiClient.get<Warehouse[]>(`${BASE}/warehouses`, { companyId }),

  createWarehouse: (companyId: string, branchId: string, payload: { name: string; is_default?: boolean }) =>
    apiClient.post<WarehouseCreateResult>(`${BASE}/warehouses`, payload, { companyId, branchId }),

  setDefaultWarehouse: (companyId: string, id: string) =>
    apiClient.post<Warehouse>(`${BASE}/warehouses/${id}:set-default`, undefined, { companyId }),

  listLocations: (companyId: string, warehouseId: string) =>
    apiClient.get<Location[]>(`${BASE}/warehouses/${warehouseId}/locations`, { companyId }),

  listStockQuants: (companyId: string) => apiClient.get<StockQuant[]>(`${BASE}/stock/quants`, { companyId }),

  listLowStock: (companyId: string) => apiClient.get<LowStockRow[]>(`${BASE}/stock/low-stock`, { companyId }),

  getStockBalance: (companyId: string, productId: string, warehouseId: string) =>
    apiClient.get<StockBalance>(
      `${BASE}/stock/balance?product_id=${productId}&warehouse_id=${warehouseId}`,
      { companyId }
    ),

  getStockBalanceByProduct: (companyId: string, productId: string) =>
    apiClient.get<StockBalanceByProduct>(`${BASE}/stock/balance-by-product?product_id=${productId}`, { companyId }),

  listStockMoves: (companyId: string, productId?: string) =>
    apiClient.get<StockMove[]>(`${BASE}/stock/moves${productId ? `?product_id=${productId}` : ""}`, { companyId }),

  receiveStock: (
    companyId: string,
    payload: { product_id: string; location_id: string; qty: string; unit_cost: string }
  ) => apiClient.post<StockMove>(`${BASE}/stock/receive`, payload, { companyId }),

  createTransfer: (
    companyId: string,
    payload: { product_id: string; source_location_id: string; dest_location_id: string; qty: string }
  ) => apiClient.post<StockMove[]>(`${BASE}/transfers`, payload, { companyId }),

  listCycleCounts: (companyId: string) => apiClient.get<CycleCount[]>(`${BASE}/cycle-counts`, { companyId }),

  getCycleCount: (companyId: string, id: string) =>
    apiClient.get<CycleCountDetail>(`${BASE}/cycle-counts/${id}`, { companyId }),

  createCycleCount: (
    companyId: string,
    payload: { warehouse_id: string; scheduled_date: string; lines: CycleCountLineIn[] }
  ) => apiClient.post<CycleCountDetail>(`${BASE}/cycle-counts`, payload, { companyId }),

  approveCycleCount: (companyId: string, branchId: string | null, id: string) =>
    apiClient.post<CycleCountDetail>(`${BASE}/cycle-counts/${id}:approve`, undefined, { companyId, branchId }),

  getProductCardex: (
    companyId: string,
    params: { productId: string; dateFrom: string; dateTo: string; warehouseId?: string; sourceTable?: string }
  ) => {
    const qs = new URLSearchParams({
      product_id: params.productId,
      date_from: params.dateFrom,
      date_to: params.dateTo,
    });
    if (params.warehouseId) qs.set("warehouse_id", params.warehouseId);
    if (params.sourceTable) qs.set("source_table", params.sourceTable);
    return apiClient.get<ProductCardex>(`${BASE}/stock/cardex?${qs.toString()}`, { companyId });
  },
};
