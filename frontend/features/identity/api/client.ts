import { apiClient } from "@/lib/api-client";
import type {
  Branch,
  BootstrapRequest,
  BootstrapResponse,
  Company,
  LoginRequest,
  MyPermissions,
  Partner,
  PartnerWriteInput,
  Product,
  ProductCategory,
  ProductWriteInput,
  TokenResponse,
  TwoFactorRequiredResponse,
  UnitOfMeasure,
} from "./types";

const BASE = "/api/v1/identity";

function qs(params: Record<string, string | boolean | undefined | null>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
}

export const identityApi = {
  bootstrap: (payload: BootstrapRequest) =>
    apiClient.post<BootstrapResponse>(`${BASE}/bootstrap`, payload, { skipAuth: true }),

  login: (payload: LoginRequest) =>
    apiClient.post<TokenResponse | TwoFactorRequiredResponse>(`${BASE}/auth/login`, payload, { skipAuth: true }),

  verify2fa: (payload: LoginRequest & { totp_code: string }) =>
    apiClient.post<TokenResponse>(`${BASE}/auth/login/verify-2fa`, payload, { skipAuth: true }),

  getCompany: (companyId: string) => apiClient.get<Company>(`${BASE}/companies/${companyId}`, { companyId }),

  getMyPermissions: (companyId: string, branchId: string | null) =>
    apiClient.get<MyPermissions>(`${BASE}/me/permissions`, { companyId, branchId }),

  listBranches: (companyId: string) =>
    apiClient.get<Branch[]>(`${BASE}/companies/${companyId}/branches`, { companyId }),

  listPartners: (
    companyId: string,
    branchId: string | null,
    opts?: { customersOnly?: boolean; vendorsOnly?: boolean; search?: string }
  ) =>
    apiClient.get<Partner[]>(
      `${BASE}/partners${qs({
        customers_only: opts?.customersOnly,
        vendors_only: opts?.vendorsOnly,
        search: opts?.search,
      })}`,
      { companyId, branchId }
    ),

  getPartner: (companyId: string, id: string) => apiClient.get<Partner>(`${BASE}/partners/${id}`, { companyId }),

  createPartner: (companyId: string, branchId: string | null, payload: PartnerWriteInput) =>
    apiClient.post<Partner>(`${BASE}/partners`, payload, { companyId, branchId }),

  updatePartner: (companyId: string, id: string, payload: PartnerWriteInput) =>
    apiClient.patch<Partner>(`${BASE}/partners/${id}`, payload, { companyId }),

  listProducts: (companyId: string, branchId: string | null, opts?: { categoryId?: string; search?: string }) =>
    apiClient.get<Product[]>(
      `${BASE}/products${qs({ category_id: opts?.categoryId, search: opts?.search })}`,
      { companyId, branchId }
    ),

  getProduct: (companyId: string, id: string) => apiClient.get<Product>(`${BASE}/products/${id}`, { companyId }),

  createProduct: (companyId: string, branchId: string | null, payload: ProductWriteInput) =>
    apiClient.post<Product>(`${BASE}/products`, payload, { companyId, branchId }),

  updateProduct: (companyId: string, id: string, payload: ProductWriteInput) =>
    apiClient.patch<Product>(`${BASE}/products/${id}`, payload, { companyId }),

  listProductCategories: (companyId: string) =>
    apiClient.get<ProductCategory[]>(`${BASE}/product-categories`, { companyId }),

  createProductCategory: (companyId: string, payload: { name: string; parent_id?: string | null }) =>
    apiClient.post<ProductCategory>(`${BASE}/product-categories`, payload, { companyId }),

  updateProductCategory: (companyId: string, id: string, payload: { name: string; parent_id: string | null }) =>
    apiClient.patch<ProductCategory>(`${BASE}/product-categories/${id}`, payload, { companyId }),

  deleteProductCategory: (companyId: string, id: string) =>
    apiClient.delete<void>(`${BASE}/product-categories/${id}`, { companyId }),

  listUom: (companyId: string, opts?: { active?: boolean; search?: string }) =>
    apiClient.get<UnitOfMeasure[]>(
      `${BASE}/uom${qs({ active: opts?.active === undefined ? undefined : String(opts.active), search: opts?.search })}`,
      { companyId }
    ),

  createUom: (companyId: string, payload: { name: string; name_ar?: string | null; code: string }) =>
    apiClient.post<UnitOfMeasure>(`${BASE}/uom`, payload, { companyId }),

  updateUom: (
    companyId: string,
    id: string,
    payload: { name: string; name_ar?: string | null; code: string; active: boolean }
  ) => apiClient.patch<UnitOfMeasure>(`${BASE}/uom/${id}`, payload, { companyId }),
};
