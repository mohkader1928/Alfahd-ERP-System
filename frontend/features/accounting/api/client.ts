import { apiClient } from "@/lib/api-client";
import type { Account, JournalEntry, JournalEntryDetail, JournalEntryLineIn, TrialBalanceRow } from "./types";

const BASE = "/api/v1/accounting";

export const accountingApi = {
  listAccounts: (companyId: string) => apiClient.get<Account[]>(`${BASE}/chart-of-accounts`, { companyId }),

  createAccount: (
    companyId: string,
    payload: { code: string; name: string; name_ar?: string; account_type_code: string; parent_id?: string | null }
  ) => apiClient.post<Account>(`${BASE}/chart-of-accounts`, payload, { companyId }),

  listJournalEntries: (companyId: string) => apiClient.get<JournalEntry[]>(`${BASE}/journal-entries`, { companyId }),

  getJournalEntry: (companyId: string, id: string) =>
    apiClient.get<JournalEntryDetail>(`${BASE}/journal-entries/${id}`, { companyId }),

  createJournalEntry: (
    companyId: string,
    branchId: string,
    payload: { journal_code: string; entry_date: string; reference?: string; lines: JournalEntryLineIn[] }
  ) => apiClient.post<JournalEntry>(`${BASE}/journal-entries`, payload, { companyId, branchId }),

  postJournalEntry: (companyId: string, id: string) =>
    apiClient.post<JournalEntry>(`${BASE}/journal-entries/${id}:post`, undefined, { companyId }),

  reverseJournalEntry: (companyId: string, id: string) =>
    apiClient.post<JournalEntry>(`${BASE}/journal-entries/${id}:reverse`, undefined, { companyId }),

  trialBalance: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<TrialBalanceRow[]>(`${BASE}/reports/trial-balance?date_from=${dateFrom}&date_to=${dateTo}`, {
      companyId,
    }),
};
