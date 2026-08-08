export interface Account {
  id: string;
  company_id: string;
  code: string;
  name: string;
  name_ar: string | null;
  parent_id: string | null;
  is_active: boolean;
}

export interface JournalEntryLineIn {
  account_id: string;
  debit: string;
  credit: string;
  description?: string;
}

export interface JournalEntry {
  id: string;
  company_id: string;
  journal_id: string;
  entry_date: string;
  reference: string | null;
  description: string | null;
  status: "draft" | "posted" | "reversed";
  source_table: string | null;
  source_id: string | null;
}

export interface JournalEntryLine {
  id: string;
  account_id: string;
  cost_center_id: string | null;
  debit: string;
  credit: string;
  description: string | null;
}

export interface JournalEntryDetail {
  entry: JournalEntry;
  lines: JournalEntryLine[];
}

export interface TrialBalanceRow {
  account_id: string;
  account_code: string;
  account_name: string;
  account_type_code: "asset" | "liability" | "equity" | "revenue" | "expense";
  opening_balance: string;
  period_debit: string;
  period_credit: string;
  closing_balance: string;
  /** @deprecated use period_debit */
  total_debit: string;
  /** @deprecated use period_credit */
  total_credit: string;
}

export interface GeneralLedgerLine {
  journal_entry_id: string;
  entry_date: string;
  reference: string | null;
  status: "draft" | "posted" | "reversed";
  debit: string;
  credit: string;
  description: string | null;
  running_balance: string;
  source_table: string | null;
  source_id: string | null;
}

export interface GeneralLedgerResponse {
  account_id: string;
  account_code: string;
  account_name: string;
  opening_balance: string;
  lines: GeneralLedgerLine[];
  closing_balance: string;
}

export interface AccountAmountRow {
  account_id: string;
  account_code: string;
  account_name: string;
  amount: string;
}

export interface IncomeStatementResponse {
  date_from: string;
  date_to: string;
  revenue_accounts: AccountAmountRow[];
  revenue_total: string;
  cogs_accounts: AccountAmountRow[];
  cogs_total: string;
  gross_profit: string;
  opex_accounts: AccountAmountRow[];
  opex_total: string;
  operating_income: string;
  net_income: string;
}

export interface BalanceSheetResponse {
  as_of_date: string;
  assets: AccountAmountRow[];
  assets_total: string;
  liabilities: AccountAmountRow[];
  liabilities_total: string;
  equity: AccountAmountRow[];
  equity_total: string;
  current_earnings: string;
  total_liabilities_and_equity: string;
}
