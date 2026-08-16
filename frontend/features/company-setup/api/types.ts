// Adaptive ERP Stage 2.5 -- types mirror the backend response_model/schema
// shapes from backend/src/modules/company_profile/api/schemas.py 1:1.
// Backend is the sole source of truth: nothing here is computed, only
// displayed.

export type ApprovalRigor = "low" | "medium" | "high";

export interface CompanyProfileWriteInput {
  industry?: string | null;
  legal_form?: string | null;
  employee_count?: number | null;
  branch_count?: number | null;
  cost_center_tracking_needed?: boolean | null;
  is_service_business?: boolean | null;
  warehouse_count?: number | null;
  monthly_sales_order_volume?: number | null;
  monthly_purchase_order_volume?: number | null;
  sku_count_estimate?: number | null;
  coa_depth_preference?: number | null;
  multi_currency_requested?: boolean | null;
  withholding_tax_needed?: boolean | null;
  owns_fixed_assets?: boolean | null;
  fixed_asset_count_estimate?: number | null;
  approval_rigor_preference?: ApprovalRigor | null;
  desired_user_count?: number | null;
  two_factor_required?: boolean | null;
  growth_notes?: Record<string, unknown> | null;
}

export interface CompanyProfile {
  id: string;
  company_id: string;
  industry: string | null;
  legal_form: string | null;
  employee_count: number | null;
  branch_count: number | null;
  cost_center_tracking_needed: boolean;
  is_service_business: boolean;
  warehouse_count: number | null;
  monthly_sales_order_volume: number | null;
  monthly_purchase_order_volume: number | null;
  sku_count_estimate: number | null;
  coa_depth_preference: number | null;
  multi_currency_requested: boolean;
  withholding_tax_needed: boolean;
  owns_fixed_assets: boolean;
  fixed_asset_count_estimate: number | null;
  approval_rigor_preference: string;
  desired_user_count: number | null;
  two_factor_required: boolean;
  growth_notes: Record<string, unknown>;
}

export interface DimensionScore {
  score: number;
  reason: string;
}

export interface SizingResult {
  id: string;
  company_id: string;
  company_profile_id: string;
  rule_version: string;
  dimension_scores: Record<string, DimensionScore>;
  created_at: string;
}

export type DecisionCategory = "STANDARD" | "CONFIGURABLE" | "EXTENSIBLE" | "CUSTOM_DEVELOPMENT";

export interface BlueprintDecision {
  key: string;
  category: DecisionCategory;
  decision: unknown;
  reason: string;
  actionable: boolean;
}

export type BlueprintStatus = "draft" | "approved" | "superseded";

export interface ErpBlueprint {
  id: string;
  company_id: string;
  company_profile_id: string;
  sizing_result_id: string;
  blueprint_version: number;
  status: BlueprintStatus;
  decisions: BlueprintDecision[];
  enabled_modules: Record<string, boolean>;
  approved_at: string | null;
  approved_by: string | null;
  superseded_by_id: string | null;
  created_at: string;
}

export type ConfigurationPlanStatus = "draft" | "validated" | "applied" | "failed";
export type ConfigurationPlanItemStatus = "pending" | "skipped_already_applied" | "applied" | "failed";

export interface ConfigurationPlanItem {
  id: string;
  plan_id: string;
  decision_key: string;
  target_type: string;
  action: string;
  payload: Record<string, unknown>;
  status: ConfigurationPlanItemStatus;
  result: Record<string, unknown>;
  error_message: string | null;
  applied_at: string | null;
  created_at: string;
}

export interface ConfigurationPlan {
  id: string;
  company_id: string;
  blueprint_id: string;
  status: ConfigurationPlanStatus;
  validated_at: string | null;
  applied_at: string | null;
  failure_reason: string | null;
  created_at: string;
  items: ConfigurationPlanItem[];
}
