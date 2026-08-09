import { apiClient } from "@/lib/api-client";
import type {
  Account,
  AccountUpdateInput,
  BalanceSheetResponse,
  GeneralLedgerResponse,
  IncomeStatementResponse,
  JournalEntry,
  JournalEntryDetail,
  JournalEntryLineIn,
  TrialBalanceRow,
} from "./types";

const BASE = "/api/v1/accounting";

export const accountingApi = {
  listAccounts: (companyId: string) => apiClient.get<Account[]>(`${BASE}/chart-of-accounts`, { companyId }),

  createAccount: (
    companyId: string,
    payload: {
      code: string;
      name: string;
      name_ar?: string;
      account_type_code: string;
      parent_id?: string | null;
      is_group?: boolean;
    }
  ) => apiClient.post<Account>(`${BASE}/chart-of-accounts`, payload, { companyId }),

  updateAccount: (companyId: string, id: string, payload: AccountUpdateInput) =>
    apiClient.patch<Account>(`${BASE}/chart-of-accounts/${id}`, payload, { companyId }),

  deleteAccount: (companyId: string, id: string) =>
    apiClient.delete<void>(`${BASE}/chart-of-accounts/${id}`, { companyId }),

  listJournalEntries: (companyId: string) => apiClient.get<JournalEntry[]>(`${BASE}/journal-entries`, { companyId }),

  getJournalEntry: (companyId: string, id: string) =>
    apiClient.get<JournalEntryDetail>(`${BASE}/journal-entries/${id}`, { companyId }),

  createJournalEntry: (
    companyId: string,
    branchId: string,
    payload: { journal_code: string; entry_date: string; reference?: string; description?: string; lines: JournalEntryLineIn[] }
  ) => apiClient.post<JournalEntry>(`${BASE}/journal-entries`, payload, { companyId, branchId }),

  postJournalEntry: (companyId: string, id: string) =>
    apiClient.post<JournalEntry>(`${BASE}/journal-entries/${id}:post`, undefined, { companyId }),

  reverseJournalEntry: (companyId: string, id: string) =>
    apiClient.post<JournalEntry>(`${BASE}/journal-entries/${id}:reverse`, undefined, { companyId }),

  trialBalance: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<TrialBalanceRow[]>(`${BASE}/reports/trial-balance?date_from=${dateFrom}&date_to=${dateTo}`, {
      companyId,
    }),

  generalLedger: (companyId: string, accountId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<GeneralLedgerResponse>(
      `${BASE}/reports/general-ledger?account_id=${accountId}&date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),

  incomeStatement: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<IncomeStatementResponse>(
      `${BASE}/reports/income-statement?date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),

  balanceSheet: (companyId: string, asOfDate: string) =>
    apiClient.get<BalanceSheetResponse>(`${BASE}/reports/balance-sheet?as_of_date=${asOfDate}`, { companyId }),
};
