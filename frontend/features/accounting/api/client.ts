import { apiClient } from "@/lib/api-client";
import type {
  Account,
  AccountUpdateInput,
  BalanceSheetResponse,
  CashFlowResponse,
  EquityStatementResponse,
  CostCenter,
  CostCenterReportResponse,
  FiscalPeriod,
  GeneralLedgerResponse,
  IncomeStatementResponse,
  JournalEntry,
  JournalEntryDetail,
  JournalEntryLineIn,
  TaxRate,
  TrialBalanceRow,
} from "./types";

const BASE = "/api/v1/accounting";

export const accountingApi = {
  listAccounts: (companyId: string) => apiClient.get<Account[]>(`${BASE}/chart-of-accounts`, { companyId }),

  listTaxRates: (companyId: string) => apiClient.get<TaxRate[]>(`${BASE}/tax-rates`, { companyId }),

  listCostCenters: (companyId: string) => apiClient.get<CostCenter[]>(`${BASE}/cost-centers`, { companyId }),

  createCostCenter: (companyId: string, payload: { name: string; name_ar?: string | null }) =>
    apiClient.post<CostCenter>(`${BASE}/cost-centers`, payload, { companyId }),

  updateCostCenter: (
    companyId: string,
    id: string,
    payload: { name?: string; name_ar?: string | null; is_active?: boolean }
  ) => apiClient.patch<CostCenter>(`${BASE}/cost-centers/${id}`, payload, { companyId }),

  listFiscalPeriods: (companyId: string) => apiClient.get<FiscalPeriod[]>(`${BASE}/fiscal-periods`, { companyId }),

  createFiscalPeriod: (companyId: string, payload: { period_start: string; period_end: string }) =>
    apiClient.post<FiscalPeriod>(`${BASE}/fiscal-periods`, payload, { companyId }),

  closeFiscalPeriod: (companyId: string, id: string) =>
    apiClient.post<FiscalPeriod>(`${BASE}/fiscal-periods/${id}:close`, undefined, { companyId }),

  createAccount: (
    companyId: string,
    payload: {
      code: string;
      name: string;
      name_ar?: string;
      account_type_code: string;
      parent_id?: string | null;
      is_group?: boolean;
      is_cash_equivalent?: boolean;
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

  cancelJournalEntry: (companyId: string, id: string) =>
    apiClient.post<JournalEntry>(`${BASE}/journal-entries/${id}:cancel`, undefined, { companyId }),

  trialBalance: (companyId: string, dateFrom: string, dateTo: string, detailLevel?: number) =>
    apiClient.get<TrialBalanceRow[]>(
      `${BASE}/reports/trial-balance?date_from=${dateFrom}&date_to=${dateTo}${detailLevel ? `&detail_level=${detailLevel}` : ""}`,
      { companyId }
    ),

  generalLedger: (
    companyId: string,
    accountId: string,
    dateFrom: string,
    dateTo: string,
    costCenterId?: string
  ) =>
    apiClient.get<GeneralLedgerResponse>(
      `${BASE}/reports/general-ledger?account_id=${accountId}&date_from=${dateFrom}&date_to=${dateTo}${costCenterId ? `&cost_center_id=${costCenterId}` : ""}`,
      { companyId }
    ),

  incomeStatement: (
    companyId: string,
    dateFrom: string,
    dateTo: string,
    detailLevel?: number,
    costCenterId?: string
  ) =>
    apiClient.get<IncomeStatementResponse>(
      `${BASE}/reports/income-statement?date_from=${dateFrom}&date_to=${dateTo}${detailLevel ? `&detail_level=${detailLevel}` : ""}${costCenterId ? `&cost_center_id=${costCenterId}` : ""}`,
      { companyId }
    ),

  balanceSheet: (companyId: string, asOfDate: string, detailLevel?: number) =>
    apiClient.get<BalanceSheetResponse>(
      `${BASE}/reports/balance-sheet?as_of_date=${asOfDate}${detailLevel ? `&detail_level=${detailLevel}` : ""}`,
      { companyId }
    ),

  costCenterReport: (companyId: string, costCenterId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<CostCenterReportResponse>(
      `${BASE}/reports/cost-center/${costCenterId}?date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),

  cashFlowStatement: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<CashFlowResponse>(
      `${BASE}/reports/cash-flow?date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),

  equityStatement: (companyId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<EquityStatementResponse>(
      `${BASE}/reports/equity-statement?date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),
};
