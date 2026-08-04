import { apiClient } from "@/lib/api-client";
import type { Location, StockMove, StockQuant, Warehouse, WarehouseCreateResult } from "./types";

const BASE = "/api/v1/inventory";

export const inventoryApi = {
  listWarehouses: (companyId: string) => apiClient.get<Warehouse[]>(`${BASE}/warehouses`, { companyId }),

  createWarehouse: (companyId: string, branchId: string, payload: { name: string; is_default?: boolean }) =>
    apiClient.post<WarehouseCreateResult>(`${BASE}/warehouses`, payload, { companyId, branchId }),

  listLocations: (companyId: string, warehouseId: string) =>
    apiClient.get<Location[]>(`${BASE}/warehouses/${warehouseId}/locations`, { companyId }),

  listStockQuants: (companyId: string) => apiClient.get<StockQuant[]>(`${BASE}/stock/quants`, { companyId }),

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
};
