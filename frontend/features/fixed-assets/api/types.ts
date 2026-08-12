export interface FixedAssetCategory {
  id: string;
  company_id: string;
  name: string;
  parent_id: string | null;
}

export interface FixedAssetCategoryInput {
  name: string;
  parent_id: string | null;
}

export interface FixedAsset {
  id: string;
  company_id: string;
  asset_code: string;
  name: string;
  name_ar: string | null;
  category_id: string | null;
  fixed_asset_account_id: string;
  accumulated_depreciation_account_id: string;
  depreciation_expense_account_id: string;
  acquisition_date: string;
  cost: string;
  salvage_value: string;
  useful_life_months: number;
  accumulated_depreciation: string;
  net_book_value: string;
  fully_depreciated: boolean;
  status: "active" | "disposed";
  disposed_at: string | null;
  disposal_proceeds: string | null;
}

export interface FixedAssetCreateInput {
  name: string;
  name_ar?: string | null;
  category_id?: string | null;
  fixed_asset_account_id: string;
  accumulated_depreciation_account_id: string;
  depreciation_expense_account_id: string;
  funding_account_id: string;
  acquisition_date: string;
  cost: string;
  salvage_value: string;
  useful_life_months: number;
}

export interface DepreciationEntry {
  id: string;
  period_month: string;
  amount: string;
  journal_entry_id: string;
}

export interface RunDepreciationResultRow {
  asset_id: string;
  asset_code: string;
  amount?: string;
  reason?: string;
}

export interface RunDepreciationResult {
  period_month: string;
  assets_posted: number;
  assets_skipped: number;
  total_amount: string;
  posted: RunDepreciationResultRow[];
  skipped: RunDepreciationResultRow[];
}

export interface DisposeAssetInput {
  disposal_date: string;
  proceeds: string;
  proceeds_account_id?: string | null;
  gain_loss_account_id?: string | null;
}

export interface AssetCardLine {
  date: string;
  movement_type: "acquisition" | "depreciation" | "disposal";
  reference: string;
  journal_entry_id: string | null;
  cost_movement: string;
  accumulated_depreciation_movement: string;
  running_cost: string;
  running_accumulated_depreciation: string;
  running_net_book_value: string;
}

export interface AssetCard {
  asset_id: string;
  asset_code: string;
  asset_name: string;
  date_from: string;
  date_to: string;
  opening_cost: string;
  opening_accumulated_depreciation: string;
  opening_net_book_value: string;
  lines: AssetCardLine[];
  closing_cost: string;
  closing_accumulated_depreciation: string;
  closing_net_book_value: string;
}

export interface ReconciliationAccountRow {
  account_id: string;
  account_code: string;
  account_name: string;
  register_total: string;
  gl_balance: string;
  difference: string;
  matches: boolean;
}

export interface Reconciliation {
  as_of_date: string;
  accounts: ReconciliationAccountRow[];
  total_register_cost: string;
  total_register_accumulated_depreciation: string;
  total_register_net_book_value: string;
  fully_matched: boolean;
}

export interface DepreciationScheduleLine {
  period_month: string;
  asset_id: string;
  asset_code: string;
  asset_name: string;
  amount: string;
}

export interface DepreciationSchedule {
  date_from: string;
  date_to: string;
  lines: DepreciationScheduleLine[];
  total_amount: string;
}
