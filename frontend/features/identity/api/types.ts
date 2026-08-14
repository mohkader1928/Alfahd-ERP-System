export interface BootstrapRequest {
  tenant_legal_name: string;
  company_legal_name: string;
  company_legal_name_ar: string;
  vat_number: string;
  base_currency_code: string;
  valuation_method: "fifo" | "average";
  main_branch_name?: string;
  main_branch_name_ar?: string;
  admin_email: string;
  admin_full_name: string;
  admin_password: string;
}

export interface BootstrapResponse {
  tenant_id: string;
  company_id: string;
  branch_id: string;
  admin_user_id: string;
  admin_role_id: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface TwoFactorRequiredResponse {
  requires_2fa: true;
}

export interface TwoFactorSetupResponse {
  secret: string;
  provisioning_uri: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_2fa_enabled: boolean;
}

export interface Company {
  id: string;
  legal_name: string;
  legal_name_ar: string;
  vat_number: string;
  cr_number: string | null;
  valuation_method: string;
  logo_path: string | null;
  po_approval_threshold: string | null;
  fiscal_year_start_month: number;
}

export interface CompanyWriteInput {
  legal_name: string;
  legal_name_ar: string;
  vat_number: string;
  cr_number?: string | null;
  po_approval_threshold?: string | null;
  fiscal_year_start_month?: number;
}

export interface Branch {
  id: string;
  company_id: string;
  name: string;
  name_ar: string;
  is_main: boolean;
}

export interface Address {
  street?: string | null;
  city?: string | null;
  region?: string | null;
  postal_code?: string | null;
  country_code?: string | null;
}

export interface Partner {
  id: string;
  company_id: string;
  partner_code: string;
  name: string;
  name_ar: string | null;
  is_company: boolean;
  parent_partner_id: string | null;
  is_customer: boolean;
  is_vendor: boolean;
  is_employee: boolean;
  job_title: string | null;
  is_primary_contact: boolean;
  phone: string | null;
  mobile: string | null;
  email: string | null;
  website: string | null;
  vat_number: string | null;
  cr_number: string | null;
  payment_terms: string | null;
  address: Address | null;
  is_active: boolean;
  image_path: string | null;
}

export interface PartnerWriteInput {
  name: string;
  name_ar?: string | null;
  is_company?: boolean;
  parent_partner_id?: string | null;
  is_customer?: boolean;
  is_vendor?: boolean;
  is_employee?: boolean;
  job_title?: string | null;
  is_primary_contact?: boolean;
  phone?: string | null;
  mobile?: string | null;
  email?: string | null;
  website?: string | null;
  vat_number?: string | null;
  cr_number?: string | null;
  payment_terms?: string | null;
  address?: Address | null;
}

export interface PartnerAddress {
  id: string;
  company_id: string;
  partner_id: string;
  type: "billing" | "shipping" | "other";
  is_default: boolean;
  street: string | null;
  city: string | null;
  region: string | null;
  postal_code: string | null;
  country_code: string | null;
}

export interface PartnerAddressWriteInput {
  type: "billing" | "shipping" | "other";
  is_default?: boolean;
  street?: string | null;
  city?: string | null;
  region?: string | null;
  postal_code?: string | null;
  country_code?: string | null;
}

export interface Product {
  id: string;
  company_id: string;
  sku: string;
  name: string;
  name_ar: string | null;
  category_id: string | null;
  uom_id: string | null;
  is_stockable: boolean;
  sales_price: string;
  cost_price: string;
  price_high: string | null;
  price_low: string | null;
  last_purchase_price: string | null;
  default_tax_rate_id: string | null;
  reorder_point: string | null;
  image_path: string | null;
}

export interface ProductWriteInput {
  sku: string;
  name: string;
  name_ar?: string | null;
  category_id?: string | null;
  uom_id?: string | null;
  is_stockable?: boolean;
  sales_price?: string;
  cost_price?: string;
  price_high?: string | null;
  price_low?: string | null;
  default_tax_rate_id?: string | null;
  reorder_point?: string | null;
}

/** Create never accepts `sku` — the backend always system-assigns it
 * (Owner directive: no master-data business code is ever user-typed). */
export type ProductCreateInput = Omit<ProductWriteInput, "sku">;

export interface ProductCategory {
  id: string;
  company_id: string;
  name: string;
  parent_id: string | null;
}

export interface UnitOfMeasure {
  id: string;
  company_id: string;
  name: string;
  name_ar: string | null;
  code: string;
  active: boolean;
}

export interface MyPermissions {
  permission_codes: string[];
}

export interface Permission {
  id: string;
  code: string;
  scope: "screen" | "field" | "action";
}

export interface Role {
  id: string;
  name: string;
  is_system: boolean;
}

export interface RoleDetail {
  id: string;
  name: string;
  is_system: boolean;
  permission_codes: string[];
}

export interface UserListRow {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_2fa_enabled: boolean;
  role_names: string[];
}

export interface CompanyAccessRow {
  company_id: string;
  company_name: string;
  branch_id: string | null;
  branch_name: string | null;
}

export interface UserDetail {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_2fa_enabled: boolean;
  roles: Role[];
  company_access: CompanyAccessRow[];
}
