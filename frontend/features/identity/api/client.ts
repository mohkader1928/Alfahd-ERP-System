import { apiClient } from "@/lib/api-client";
import type {
  Branch,
  BootstrapRequest,
  BootstrapResponse,
  Company,
  LoginRequest,
  Partner,
  Product,
  TokenResponse,
  TwoFactorRequiredResponse,
} from "./types";

const BASE = "/api/v1/identity";

export const identityApi = {
  bootstrap: (payload: BootstrapRequest) =>
    apiClient.post<BootstrapResponse>(`${BASE}/bootstrap`, payload, { skipAuth: true }),

  login: (payload: LoginRequest) =>
    apiClient.post<TokenResponse | TwoFactorRequiredResponse>(`${BASE}/auth/login`, payload, { skipAuth: true }),

  verify2fa: (payload: LoginRequest & { totp_code: string }) =>
    apiClient.post<TokenResponse>(`${BASE}/auth/login/verify-2fa`, payload, { skipAuth: true }),

  getCompany: (companyId: string) => apiClient.get<Company>(`${BASE}/companies/${companyId}`, { companyId }),

  listBranches: (companyId: string) =>
    apiClient.get<Branch[]>(`${BASE}/companies/${companyId}/branches`, { companyId }),

  listPartners: (companyId: string, branchId: string | null, opts?: { customersOnly?: boolean; vendorsOnly?: boolean }) =>
    apiClient.get<Partner[]>(
      `${BASE}/partners${opts?.customersOnly ? "?customers_only=true" : opts?.vendorsOnly ? "?vendors_only=true" : ""}`,
      { companyId, branchId }
    ),

  createPartner: (
    companyId: string,
    branchId: string | null,
    payload: { name: string; is_customer?: boolean; is_vendor?: boolean; vat_number?: string | null }
  ) => apiClient.post<Partner>(`${BASE}/partners`, payload, { companyId, branchId }),

  listProducts: (companyId: string, branchId: string | null) =>
    apiClient.get<Product[]>(`${BASE}/products`, { companyId, branchId }),

  createProduct: (
    companyId: string,
    branchId: string | null,
    payload: { sku: string; name: string; sales_price?: string }
  ) => apiClient.post<Product>(`${BASE}/products`, payload, { companyId, branchId }),
};
