export interface FixedAsset {
  id: string;
  company_id: string;
  asset_code: string;
  name: string;
  name_ar: string | null;
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
