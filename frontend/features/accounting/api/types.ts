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
  status: "draft" | "posted" | "reversed";
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
  total_debit: string;
  total_credit: string;
}
