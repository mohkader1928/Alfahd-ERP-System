import { apiClient } from "@/lib/api-client";
import type {
  Branch,
  BootstrapRequest,
  BootstrapResponse,
  Company,
  CompanyWriteInput,
  LoginRequest,
  MyPermissions,
  Partner,
  PartnerAddress,
  PartnerAddressWriteInput,
  PartnerWriteInput,
  PasswordResetConfirmRequest,
  PasswordResetRequestRequest,
  PasswordResetResponse,
  Permission,
  Product,
  ProductCategory,
  ProductCreateInput,
  ProductWriteInput,
  Role,
  RoleDetail,
  TokenResponse,
  TwoFactorRequiredResponse,
  TwoFactorSetupResponse,
  UnitOfMeasure,
  User,
  UserDetail,
  UserListRow,
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

  requestPasswordReset: (payload: PasswordResetRequestRequest) =>
    apiClient.post<PasswordResetResponse>(`${BASE}/auth/password-reset/request`, payload, {
      skipAuth: true,
    }),

  confirmPasswordReset: (payload: PasswordResetConfirmRequest) =>
    apiClient.post<PasswordResetResponse>(`${BASE}/auth/password-reset/confirm`, payload, {
      skipAuth: true,
    }),

  getMyProfile: (companyId: string) => apiClient.get<User>(`${BASE}/me`, { companyId }),

  start2faEnrollment: (companyId: string) =>
    apiClient.post<TwoFactorSetupResponse>(`${BASE}/me/2fa/setup`, undefined, { companyId }),

  verify2faEnrollment: (companyId: string, totpCode: string) =>
    apiClient.post<User>(`${BASE}/me/2fa/verify`, { totp_code: totpCode }, { companyId }),

  getCompany: (companyId: string) => apiClient.get<Company>(`${BASE}/companies/${companyId}`, { companyId }),

  updateCompany: (companyId: string, payload: CompanyWriteInput) =>
    apiClient.patch<Company>(`${BASE}/companies/${companyId}`, payload, { companyId }),

  uploadCompanyLogo: (companyId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.post<Company>(`${BASE}/companies/${companyId}/logo`, form, { companyId });
  },

  deleteCompanyLogo: (companyId: string) =>
    apiClient.delete<Company>(`${BASE}/companies/${companyId}/logo`, { companyId }),

  getMyPermissions: (companyId: string, branchId: string | null) =>
    apiClient.get<MyPermissions>(`${BASE}/me/permissions`, { companyId, branchId }),

  listBranches: (companyId: string) =>
    apiClient.get<Branch[]>(`${BASE}/companies/${companyId}/branches`, { companyId }),

  listPartners: (
    companyId: string,
    branchId: string | null,
    opts?: {
      customersOnly?: boolean;
      vendorsOnly?: boolean;
      employeesOnly?: boolean;
      parentPartnerId?: string;
      includeArchived?: boolean;
      search?: string;
    }
  ) =>
    apiClient.get<Partner[]>(
      `${BASE}/partners${qs({
        customers_only: opts?.customersOnly,
        vendors_only: opts?.vendorsOnly,
        employees_only: opts?.employeesOnly,
        parent_partner_id: opts?.parentPartnerId,
        include_archived: opts?.includeArchived,
        search: opts?.search,
      })}`,
      { companyId, branchId }
    ),

  getPartner: (companyId: string, id: string) => apiClient.get<Partner>(`${BASE}/partners/${id}`, { companyId }),

  createPartner: (companyId: string, branchId: string | null, payload: PartnerWriteInput) =>
    apiClient.post<Partner>(`${BASE}/partners`, payload, { companyId, branchId }),

  updatePartner: (companyId: string, id: string, payload: PartnerWriteInput) =>
    apiClient.patch<Partner>(`${BASE}/partners/${id}`, payload, { companyId }),

  archivePartner: (companyId: string, id: string) =>
    apiClient.post<Partner>(`${BASE}/partners/${id}/archive`, {}, { companyId }),

  restorePartner: (companyId: string, id: string) =>
    apiClient.post<Partner>(`${BASE}/partners/${id}/restore`, {}, { companyId }),

  uploadPartnerImage: (companyId: string, id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.post<Partner>(`${BASE}/partners/${id}/image`, form, { companyId });
  },

  deletePartnerImage: (companyId: string, id: string) =>
    apiClient.delete<Partner>(`${BASE}/partners/${id}/image`, { companyId }),

  listPartnerAddresses: (companyId: string, partnerId: string) =>
    apiClient.get<PartnerAddress[]>(`${BASE}/partners/${partnerId}/addresses`, { companyId }),

  createPartnerAddress: (companyId: string, partnerId: string, payload: PartnerAddressWriteInput) =>
    apiClient.post<PartnerAddress>(`${BASE}/partners/${partnerId}/addresses`, payload, { companyId }),

  updatePartnerAddress: (companyId: string, partnerId: string, addressId: string, payload: PartnerAddressWriteInput) =>
    apiClient.patch<PartnerAddress>(`${BASE}/partners/${partnerId}/addresses/${addressId}`, payload, { companyId }),

  deletePartnerAddress: (companyId: string, partnerId: string, addressId: string) =>
    apiClient.delete<void>(`${BASE}/partners/${partnerId}/addresses/${addressId}`, { companyId }),

  listProducts: (companyId: string, branchId: string | null, opts?: { categoryId?: string; search?: string }) =>
    apiClient.get<Product[]>(
      `${BASE}/products${qs({ category_id: opts?.categoryId, search: opts?.search })}`,
      { companyId, branchId }
    ),

  getProduct: (companyId: string, id: string) => apiClient.get<Product>(`${BASE}/products/${id}`, { companyId }),

  createProduct: (companyId: string, branchId: string | null, payload: ProductCreateInput) =>
    apiClient.post<Product>(`${BASE}/products`, payload, { companyId, branchId }),

  updateProduct: (companyId: string, id: string, payload: ProductWriteInput) =>
    apiClient.patch<Product>(`${BASE}/products/${id}`, payload, { companyId }),

  uploadProductImage: (companyId: string, id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.post<Product>(`${BASE}/products/${id}/image`, form, { companyId });
  },

  deleteProductImage: (companyId: string, id: string) =>
    apiClient.delete<Product>(`${BASE}/products/${id}/image`, { companyId }),

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

  listPermissions: (companyId: string) => apiClient.get<Permission[]>(`${BASE}/permissions`, { companyId }),

  listRoles: (companyId: string) => apiClient.get<Role[]>(`${BASE}/roles`, { companyId }),

  getRole: (companyId: string, roleId: string) =>
    apiClient.get<RoleDetail>(`${BASE}/roles/${roleId}`, { companyId }),

  createRole: (companyId: string, name: string) =>
    apiClient.post<RoleDetail>(`${BASE}/roles`, { name }, { companyId }),

  updateRolePermissions: (companyId: string, roleId: string, permissionCodes: string[]) =>
    apiClient.put<RoleDetail>(
      `${BASE}/roles/${roleId}/permissions`,
      { permission_codes: permissionCodes },
      { companyId }
    ),

  renameRole: (companyId: string, roleId: string, name: string) =>
    apiClient.patch<RoleDetail>(`${BASE}/roles/${roleId}`, { name }, { companyId }),

  deleteRole: (companyId: string, roleId: string) =>
    apiClient.delete<void>(`${BASE}/roles/${roleId}`, { companyId }),

  listUsers: (companyId: string) => apiClient.get<UserListRow[]>(`${BASE}/users`, { companyId }),

  getUser: (companyId: string, userId: string) =>
    apiClient.get<UserDetail>(`${BASE}/users/${userId}`, { companyId }),

  createUser: (
    companyId: string,
    payload: { email: string; full_name: string; password: string; branch_id?: string | null }
  ) => apiClient.post<UserListRow>(`${BASE}/users`, { ...payload, company_id: companyId }, { companyId }),

  assignRole: (companyId: string, userId: string, roleId: string) =>
    apiClient.post<void>(`${BASE}/users/${userId}/roles`, { role_id: roleId }, { companyId }),

  removeRole: (companyId: string, userId: string, roleId: string) =>
    apiClient.delete<void>(`${BASE}/users/${userId}/roles/${roleId}`, { companyId }),

  grantCompanyAccess: (companyId: string, userId: string, payload: { company_id: string; branch_id?: string | null }) =>
    apiClient.post<void>(`${BASE}/users/${userId}/company-access`, payload, { companyId }),
};
