"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import type { Account, JournalEntry, JournalEntryLineIn } from "@/features/accounting/api/types";
import { identityApi } from "@/features/identity/api/client";
import { paymentsApi } from "@/features/payments/api/client";
import { reportingApi } from "@/features/reporting/api/client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";
import type { AgingRow, SubledgerLine } from "@/features/payments/api/types";
import { ApiError } from "@/lib/api-client";
import { reportExportHandlers } from "@/lib/report-export";
import { sourceDocumentHref, sourceDocumentLabelKey } from "@/lib/source-document-links";

const ACCOUNT_TYPE_CODES = ["asset", "liability", "equity", "revenue", "expense"] as const;
const JOURNAL_CODES = ["GEN", "SALES", "PURCH", "BANK", "CASH"] as const;

function ChartOfAccountsTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [accountTypeCode, setAccountTypeCode] = useState<string>("asset");
  const [error, setError] = useState<string | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["accounts", companyId],
    queryFn: () => accountingApi.listAccounts(companyId),
  });

  const createMutation = useMutation({
    mutationFn: () => accountingApi.createAccount(companyId, { code, name, account_type_code: accountTypeCode }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts", companyId] });
      toastSuccess(t("toast.success_title"), name);
      setCode("");
      setName("");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  const columns: ERPColumn<Account>[] = [
    { key: "code", header: t("accounting.accounts.code"), sortable: true, sortValue: (r) => r.code, render: (r) => <span className="font-mono">{r.code}</span> },
    { key: "name", header: t("accounting.accounts.name"), sortable: true, sortValue: (r) => r.name, render: (r) => r.name },
    { key: "name_ar", header: t("master_data.partners.name_ar"), render: (r) => r.name_ar ?? "—" },
    {
      key: "is_active",
      header: t("accounting.accounts.active"),
      render: (r) => <Badge variant={r.is_active ? "default" : "secondary"}>{r.is_active ? t("common.active") : t("common.inactive")}</Badge>,
    },
  ];

  return (
    <div className="space-y-4">
      <Can permission="accounting.chart_of_accounts.manage">
        <Card>
          <CardHeader>
            <CardTitle>{t("accounting.accounts.new")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.accounts.code")}</Label>
                <Input value={code} onChange={(e) => setCode(e.target.value)} className="w-28" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.accounts.name")}</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.accounts.type")}</Label>
                <Select value={accountTypeCode} onValueChange={(v) => setAccountTypeCode(v ?? "asset")}>
                  <SelectTrigger className="w-36">
                    <SelectValue>{(value: string) => value}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {ACCOUNT_TYPE_CODES.map((code) => (
                      <SelectItem key={code} value={code}>
                        {code}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button
                size="sm"
                onClick={() => {
                  setError(null);
                  createMutation.mutate();
                }}
                disabled={!code || !name || createMutation.isPending}
              >
                <Plus className="h-4 w-4" />
                {t("accounting.accounts.save")}
              </Button>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </Can>
      <ERPListView
        title={t("accounting.tabs.accounts")}
        columns={columns}
        rows={accountsQuery.data}
        rowKey={(r) => r.id}
        isLoading={accountsQuery.isLoading}
        isError={accountsQuery.isError}
        onRetry={() => accountsQuery.refetch()}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["accounts", companyId] })}
        searchText={(r) => `${r.code} ${r.name} ${r.name_ar ?? ""}`}
        searchPlaceholder={t("list.search_placeholder")}
        emptyDescription={t("common.empty")}
      />
    </div>
  );
}

function JournalEntriesTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;
  const queryClient = useQueryClient();

  const [journalCode, setJournalCode] = useState<string>("GEN");
  const [entryDate, setEntryDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [reference, setReference] = useState("");
  const [description, setDescription] = useState("");
  const [lines, setLines] = useState<JournalEntryLineIn[]>([
    { account_id: "", debit: "0", credit: "0" },
    { account_id: "", debit: "0", credit: "0" },
  ]);
  const [error, setError] = useState<string | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["accounts", companyId],
    queryFn: () => accountingApi.listAccounts(companyId),
  });
  const entriesQuery = useQuery({
    queryKey: ["journal-entries", companyId],
    queryFn: () => accountingApi.listJournalEntries(companyId),
  });

  const totalDebit = lines.reduce((sum, l) => sum + (Number(l.debit) || 0), 0);
  const totalCredit = lines.reduce((sum, l) => sum + (Number(l.credit) || 0), 0);
  const balanced = lines.length >= 2 && totalDebit === totalCredit && totalDebit > 0;

  const createMutation = useMutation({
    mutationFn: () =>
      accountingApi.createJournalEntry(companyId, branchId, {
        journal_code: journalCode,
        entry_date: entryDate,
        reference: reference || undefined,
        description: description || undefined,
        lines,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["journal-entries", companyId] });
      toastSuccess(t("toast.success_title"), t("accounting.je.save"));
      setReference("");
      setDescription("");
      setLines([
        { account_id: "", debit: "0", credit: "0" },
        { account_id: "", debit: "0", credit: "0" },
      ]);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  function updateLine(index: number, patch: Partial<JournalEntryLineIn>) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  const columns: ERPColumn<JournalEntry>[] = [
    { key: "entry_date", header: t("accounting.je.date"), sortable: true, sortValue: (r) => r.entry_date, render: (r) => formatDate(r.entry_date, locale) },
    {
      key: "reference",
      header: t("accounting.je.reference"),
      sortable: true,
      sortValue: (r) => r.reference ?? "",
      render: (r) => (
        <Link href={`/accounting/journal-entries/${r.id}`} className="font-medium underline-offset-4 hover:underline">
          {r.reference ?? r.id.slice(0, 8)}
        </Link>
      ),
    },
    {
      key: "status",
      header: t("accounting.je.status"),
      render: (r) => <Badge variant={statusVariant(r.status)}>{r.status}</Badge>,
    },
  ];

  return (
    <div className="space-y-4">
      <Can permission="accounting.journal_entry.create">
        <Card>
          <CardHeader>
            <CardTitle>{t("accounting.je.new")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.je.journal_code")}</Label>
                <Select value={journalCode} onValueChange={(v) => setJournalCode(v ?? "GEN")}>
                  <SelectTrigger className="w-32">
                    <SelectValue>{(value: string) => value}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {JOURNAL_CODES.map((code) => (
                      <SelectItem key={code} value={code}>
                        {code}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.je.date")}</Label>
                <Input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} className="w-40" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.je.reference")}</Label>
                <Input value={reference} onChange={(e) => setReference(e.target.value)} className="w-48" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("accounting.je.description")}</Label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder={t("accounting.je.description_placeholder")}
              />
            </div>
            <div className="space-y-2">
              {lines.map((line, index) => (
                <div key={index} className="flex items-end gap-2">
                  <div className="flex-1 space-y-1">
                    <Label className="text-xs">{t("accounting.je.account")}</Label>
                    <Select value={line.account_id} onValueChange={(v) => updateLine(index, { account_id: v ?? "" })}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t("accounting.je.account")}>
                          {(value: string) => {
                            const acc = accountsQuery.data?.find((a) => a.id === value);
                            return acc ? `${acc.code} — ${acc.name}` : value;
                          }}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {accountsQuery.data?.map((a) => (
                          <SelectItem key={a.id} value={a.id}>
                            {a.code} — {a.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="w-28 space-y-1">
                    <Label className="text-xs">{t("accounting.je.debit")}</Label>
                    <Input value={line.debit} onChange={(e) => updateLine(index, { debit: e.target.value })} />
                  </div>
                  <div className="w-28 space-y-1">
                    <Label className="text-xs">{t("accounting.je.credit")}</Label>
                    <Input value={line.credit} onChange={(e) => updateLine(index, { credit: e.target.value })} />
                  </div>
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setLines((prev) => [...prev, { account_id: "", debit: "0", credit: "0" }])}
              >
                <Plus className="h-4 w-4" />
                {t("accounting.je.add_line")}
              </Button>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className={balanced ? "text-muted-foreground" : "text-destructive"}>
                {formatCurrency(totalDebit)} / {formatCurrency(totalCredit)}
                {!balanced && ` — ${t("accounting.je.unbalanced")}`}
              </span>
              <Button
                size="sm"
                onClick={() => {
                  setError(null);
                  createMutation.mutate();
                }}
                disabled={!balanced || lines.some((l) => !l.account_id) || createMutation.isPending}
              >
                {createMutation.isPending ? t("common.loading") : t("accounting.je.save")}
              </Button>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </Can>
      <ERPListView
        title={t("accounting.tabs.journal_entries")}
        columns={columns}
        rows={entriesQuery.data}
        rowKey={(r) => r.id}
        getRowHref={(r) => `/accounting/journal-entries/${r.id}`}
        isLoading={entriesQuery.isLoading}
        isError={entriesQuery.isError}
        onRetry={() => entriesQuery.refetch()}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["journal-entries", companyId] })}
        searchText={(r) => `${r.reference ?? ""} ${r.entry_date} ${r.status}`}
        searchPlaceholder={t("list.search_placeholder")}
        emptyDescription={t("common.empty")}
      />
    </div>
  );
}

/** Returns the sign-adjusted closing balance for display.
 * Debit-normal accounts (asset, expense): positive closing = debit balance → show in Dr column.
 * Credit-normal accounts (liability, equity, revenue): positive closing = credit balance → show in Cr column.
 * The raw `closing_balance` from the API is always debit-minus-credit (positive = net debit).
 */
function tbBalanceCells(row: { account_type_code: string; closing_balance: string }) {
  const raw = Number(row.closing_balance); // debit-minus-credit; positive = net debit
  const isDebitNormal = row.account_type_code === "asset" || row.account_type_code === "expense";
  return {
    // A trial balance always places an account's ACTUAL net position in the
    // matching Dr/Cr column, regardless of the account type's expected
    // normal side — a liability account can genuinely carry a debit balance
    // (e.g. VAT Payable when input VAT from purchases exceeds output VAT
    // from sales in the period). Gating display by the "expected" side
    // silently dropped the balance for every such account and broke the
    // fundamental total-Dr-equals-total-Cr invariant.
    drBalance: raw > 0 ? raw : 0,
    crBalance: raw < 0 ? -raw : 0,
    /** true when the balance is on the "wrong" side for this account type —
     * unusual but legitimate; the number is still shown, just flagged. */
    isAbnormal: (isDebitNormal && raw < 0) || (!isDebitNormal && raw > 0),
  };
}

function TrialBalanceTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ from: string; to: string } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["trial-balance", companyId, ranAt?.from, ranAt?.to],
    queryFn: () => accountingApi.trialBalance(companyId, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  const rows = reportQuery.data ?? [];
  const totalPeriodDebit = rows.reduce((s, r) => s + Number(r.period_debit), 0);
  const totalPeriodCredit = rows.reduce((s, r) => s + Number(r.period_credit), 0);
  const totalOpeningDr = rows.reduce((s, r) => s + Math.max(Number(r.opening_balance), 0), 0);
  const totalOpeningCr = rows.reduce((s, r) => s + Math.max(-Number(r.opening_balance), 0), 0);
  const totalClosingDr = rows.reduce((s, r) => s + tbBalanceCells(r).drBalance, 0);
  const totalClosingCr = rows.reduce((s, r) => s + tbBalanceCells(r).crBalance, 0);

  return (
    <ReportView
      title={t("accounting.tabs.trial_balance")}
      filterArea={
        <>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
        </>
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo })}
      onPrint={ranAt && reportQuery.data ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/accounting/reports/trial-balance",
            { date_from: ranAt.from, date_to: ranAt.to, lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!ranAt && !reportQuery.isLoading && rows.length === 0}
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.tb.run_hint")}</p>}
      {ranAt && reportQuery.data && (
        <>
          <ReportPrintHeader reportTitle={t("accounting.tabs.trial_balance")} dateRangeLabel={`${ranAt.from} – ${ranAt.to}`} />
          <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {/* Account info */}
                <TableHead rowSpan={2} className="align-bottom w-24">{t("accounting.accounts.code")}</TableHead>
                <TableHead rowSpan={2} className="align-bottom">{t("accounting.accounts.name")}</TableHead>
                {/* Opening balance group */}
                <TableHead colSpan={2} className="text-center border-s">{t("accounting.tb.opening_balance")}</TableHead>
                {/* Period movement group */}
                <TableHead colSpan={2} className="text-center border-s">{t("accounting.tb.period_movement")}</TableHead>
                {/* Closing balance group */}
                <TableHead colSpan={2} className="text-center border-s">{t("accounting.tb.closing_balance")}</TableHead>
              </TableRow>
              <TableRow>
                <TableHead className="text-end border-s">{t("accounting.tb.debit")}</TableHead>
                <TableHead className="text-end">{t("accounting.tb.credit")}</TableHead>
                <TableHead className="text-end border-s">{t("accounting.tb.debit")}</TableHead>
                <TableHead className="text-end">{t("accounting.tb.credit")}</TableHead>
                <TableHead className="text-end border-s">{t("accounting.tb.debit")}</TableHead>
                <TableHead className="text-end">{t("accounting.tb.credit")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => {
                const openRaw = Number(row.opening_balance);
                const { drBalance, crBalance, isAbnormal } = tbBalanceCells(row);
                return (
                  <TableRow key={row.account_id} className={isAbnormal ? "bg-yellow-50 dark:bg-yellow-950/20" : ""}>
                    <TableCell className="font-mono text-sm">{row.account_code}</TableCell>
                    <TableCell>
                      <Link
                        href={`/accounting?tab=general-ledger&account=${row.account_id}`}
                        className="underline-offset-4 hover:underline"
                        title={t("accounting.tb.drill_down_hint")}
                      >
                        {row.account_name}
                      </Link>
                    </TableCell>
                    {/* Opening */}
                    <TableCell className="text-end font-mono border-s">
                      {openRaw > 0 ? formatCurrency(openRaw) : "—"}
                    </TableCell>
                    <TableCell className="text-end font-mono">
                      {openRaw < 0 ? formatCurrency(-openRaw) : "—"}
                    </TableCell>
                    {/* Period */}
                    <TableCell className="text-end font-mono border-s">
                      {Number(row.period_debit) > 0 ? formatCurrency(row.period_debit) : "—"}
                    </TableCell>
                    <TableCell className="text-end font-mono">
                      {Number(row.period_credit) > 0 ? formatCurrency(row.period_credit) : "—"}
                    </TableCell>
                    {/* Closing */}
                    <TableCell className={`text-end font-mono border-s${isAbnormal ? " text-amber-600 dark:text-amber-400" : ""}`}>
                      {drBalance > 0 ? formatCurrency(drBalance) : "—"}
                    </TableCell>
                    <TableCell className={`text-end font-mono${isAbnormal ? " text-amber-600 dark:text-amber-400" : ""}`}>
                      {crBalance > 0 ? formatCurrency(crBalance) : "—"}
                    </TableCell>
                  </TableRow>
                );
              })}
              {/* Totals row */}
              <TableRow className="font-semibold border-t-2">
                <TableCell colSpan={2}>{t("accounting.tb.total")}</TableCell>
                <TableCell className="text-end border-s">{formatCurrency(totalOpeningDr)}</TableCell>
                <TableCell className="text-end">{formatCurrency(totalOpeningCr)}</TableCell>
                <TableCell className="text-end border-s">{formatCurrency(totalPeriodDebit)}</TableCell>
                <TableCell className="text-end">{formatCurrency(totalPeriodCredit)}</TableCell>
                <TableCell className="text-end border-s">{formatCurrency(totalClosingDr)}</TableCell>
                <TableCell className="text-end">{formatCurrency(totalClosingCr)}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
          </div>
        </>
      )}
    </ReportView>
  );
}

function GeneralLedgerTab({ initialAccountId }: { initialAccountId?: string }) {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [accountId, setAccountId] = useState(initialAccountId ?? "");
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ account: string; from: string; to: string } | null>(() =>
    initialAccountId ? { account: initialAccountId, from: new Date().toISOString().slice(0, 8) + "01", to: new Date().toISOString().slice(0, 10) } : null
  );

  const accountsQuery = useQuery({
    queryKey: ["accounts", companyId],
    queryFn: () => accountingApi.listAccounts(companyId),
  });
  const reportQuery = useQuery({
    queryKey: ["general-ledger", companyId, ranAt?.account, ranAt?.from, ranAt?.to],
    queryFn: () => accountingApi.generalLedger(companyId, ranAt!.account, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  return (
    <ReportView
      title={t("accounting.tabs.general_ledger")}
      filterArea={
        <>
          <div className="w-64 space-y-1">
            <Label className="text-xs">{t("accounting.gl.select_account")}</Label>
            <Select value={accountId} onValueChange={(v) => setAccountId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("accounting.gl.select_account")}>
                  {(value: string) => {
                    const acc = accountsQuery.data?.find((a) => a.id === value);
                    return acc ? `${acc.code} — ${acc.name}` : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {accountsQuery.data?.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.code} — {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
        </>
      }
      onApply={accountId ? () => setRanAt({ account: accountId, from: dateFrom, to: dateTo }) : undefined}
      onPrint={ranAt && reportQuery.data ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/accounting/reports/general-ledger",
            { account_id: ranAt.account, date_from: ranAt.from, date_to: ranAt.to, lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!ranAt && !!reportQuery.data && reportQuery.data.lines.length === 0}
      kpis={
        ranAt && reportQuery.data
          ? [
              { label: t("accounting.gl.opening_balance"), value: formatCurrency(reportQuery.data.opening_balance) },
              { label: t("accounting.gl.closing_balance"), value: formatCurrency(reportQuery.data.closing_balance) },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.gl.select_account_hint")}</p>}
      {ranAt && reportQuery.data && (
        <>
        <ReportPrintHeader reportTitle={t("accounting.tabs.general_ledger")} dateRangeLabel={`${ranAt.from} – ${ranAt.to}`} />
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("accounting.gl.date")}</TableHead>
              <TableHead>{t("accounting.gl.reference")}</TableHead>
              <TableHead>{t("accounting.sub.source")}</TableHead>
              <TableHead className="text-end">{t("accounting.je.debit")}</TableHead>
              <TableHead className="text-end">{t("accounting.je.credit")}</TableHead>
              <TableHead className="text-end">{t("accounting.gl.running_balance")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {reportQuery.data.lines.map((line, i) => {
              const sourceHref = sourceDocumentHref(line.source_table, line.source_id);
              const sourceLabelKey = sourceDocumentLabelKey(line.source_table);
              return (
                <TableRow key={i}>
                  <TableCell>{formatDate(line.entry_date, locale)}</TableCell>
                  <TableCell>
                    <Link
                      href={`/accounting/journal-entries/${line.journal_entry_id}`}
                      className="underline-offset-4 hover:underline"
                    >
                      {line.reference ?? line.journal_entry_id.slice(0, 8)}
                    </Link>
                  </TableCell>
                  <TableCell>
                    {sourceLabelKey ? (
                      sourceHref ? (
                        <Link href={sourceHref} className="underline-offset-4 hover:underline">
                          {t(sourceLabelKey)}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">{t(sourceLabelKey)}</span>
                      )
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(line.debit)}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(line.credit)}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(line.running_balance)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        </>
      )}
    </ReportView>
  );
}

/**
 * Shared component: a labelled section in a financial statement (Income
 * Statement or Balance Sheet) — renders a group header, one row per
 * account with code + name (drill-down link to GL) + amount, and a
 * subtotal/total row.  The `sign` prop controls whether amounts in this
 * section are displayed as-is (+1) or negated (-1) for presentation
 * purposes (e.g. expenses shown as deductions are negated).
 */
function FinancialSection({
  label,
  rows,
  total,
  totalLabel,
  sign = 1,
  totalBorder = "single",
}: {
  label: string;
  rows: { account_id: string; account_code: string; account_name: string; amount: string }[];
  total: string;
  totalLabel: string;
  sign?: 1 | -1;
  totalBorder?: "single" | "double";
}) {
  const { t } = useI18n();
  const totalNum = Number(total) * sign;
  return (
    <tbody>
      {/* Section header */}
      <tr>
        <td colSpan={3} className="pt-4 pb-1 font-semibold text-sm font-sans">
          {label}
        </td>
      </tr>
      {/* Account rows */}
      {rows.map((row) => {
        const amount = Number(row.amount) * sign;
        return (
          <tr key={row.account_id}>
            <td className="ps-4 py-0.5 font-mono text-xs text-muted-foreground w-20 align-top">
              {row.account_code}
            </td>
            <td className="ps-2 py-0.5 text-sm text-muted-foreground">
              <Link
                href={`/accounting?tab=general-ledger&account=${row.account_id}`}
                className="underline-offset-4 hover:underline"
                title={t("accounting.tb.drill_down_hint")}
              >
                {row.account_name}
              </Link>
            </td>
            <td className="py-0.5 text-end font-mono text-sm tabular-nums text-muted-foreground">
              {formatCurrency(Math.abs(amount))}
            </td>
          </tr>
        );
      })}
      {/* Total row */}
      <tr
        className={
          totalBorder === "double"
            ? "border-t-2 border-double font-bold text-base"
            : "border-t font-semibold"
        }
      >
        <td className="py-1" />
        <td className="py-1 text-sm font-sans">{totalLabel}</td>
        <td className="py-1 text-end font-mono tabular-nums">{formatCurrency(Math.abs(totalNum))}</td>
      </tr>
    </tbody>
  );
}

function IncomeStatementTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ from: string; to: string } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["income-statement", companyId, ranAt?.from, ranAt?.to],
    queryFn: () => accountingApi.incomeStatement(companyId, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });
  const r = reportQuery.data;

  return (
    <ReportView
      title={t("accounting.tabs.income_statement")}
      filterArea={
        <>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.is.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.is.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
        </>
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo })}
      onPrint={r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/accounting/reports/income-statement",
            { date_from: ranAt.from, date_to: ranAt.to, lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      kpis={
        r
          ? [
              { label: t("accounting.is.gross_profit"), value: formatCurrency(r.gross_profit) },
              { label: t("accounting.is.net_income"), value: formatCurrency(r.net_income) },
            ]
          : undefined
      }
    >
      {!r && <p className="text-sm text-muted-foreground">{t("accounting.gl.select_account_hint")}</p>}
      {r && (
        <div className="max-w-lg">
          <ReportPrintHeader
            reportTitle={t("accounting.tabs.income_statement")}
            dateRangeLabel={ranAt ? `${ranAt.from} – ${ranAt.to}` : undefined}
          />
          <table className="w-full border-collapse">
            {/* Revenue */}
            <FinancialSection
              label={t("accounting.is.revenue")}
              rows={r.revenue_accounts}
              total={r.revenue_total}
              totalLabel={t("accounting.is.total_revenue")}
            />
            {/* COGS — shown as a deduction (negated for display) */}
            <FinancialSection
              label={t("accounting.is.cogs")}
              rows={r.cogs_accounts}
              total={r.cogs_total}
              totalLabel={t("accounting.is.total_cogs")}
              sign={-1}
            />
            {/* Gross Profit subtotal */}
            <tbody>
              <tr className="border-t-2 font-bold">
                <td className="py-1.5 w-20" />
                <td className="py-1.5 font-sans">{t("accounting.is.gross_profit")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.gross_profit)}</td>
              </tr>
            </tbody>
            {/* Operating Expenses — shown as deductions */}
            <FinancialSection
              label={t("accounting.is.opex")}
              rows={r.opex_accounts}
              total={r.opex_total}
              totalLabel={t("accounting.is.total_opex")}
              sign={-1}
            />
            {/* Operating Income */}
            <tbody>
              <tr className="border-t font-semibold">
                <td className="py-1.5 w-20" />
                <td className="py-1.5 font-sans">{t("accounting.is.operating_income")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.operating_income)}</td>
              </tr>
              {/* Net Income — double border */}
              <tr className="border-t-2 border-double font-bold text-base">
                <td className="py-2 w-20" />
                <td className="py-2 font-sans">{t("accounting.is.net_income")}</td>
                <td className="py-2 text-end font-mono tabular-nums">{formatCurrency(r.net_income)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </ReportView>
  );
}

function BalanceSheetTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [asOfDate, setAsOfDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<string | null>(null);

  const reportQuery = useQuery({
    queryKey: ["balance-sheet", companyId, ranAt],
    queryFn: () => accountingApi.balanceSheet(companyId, ranAt!),
    enabled: !!ranAt,
  });
  const r = reportQuery.data;

  return (
    <ReportView
      title={t("accounting.tabs.balance_sheet")}
      filterArea={
        <div className="space-y-1">
          <Label className="text-xs">{t("accounting.bs.as_of_date")}</Label>
          <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-40" />
        </div>
      }
      onApply={() => setRanAt(asOfDate)}
      onPrint={r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/accounting/reports/balance-sheet",
            { as_of_date: ranAt, lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      kpis={
        r
          ? [
              { label: t("accounting.bs.total_assets"), value: formatCurrency(r.assets_total) },
              { label: t("accounting.bs.total_liabilities_and_equity"), value: formatCurrency(r.total_liabilities_and_equity) },
            ]
          : undefined
      }
    >
      {!r && <p className="text-sm text-muted-foreground">{t("accounting.gl.select_account_hint")}</p>}
      {r && (
        <div className="grid max-w-4xl grid-cols-1 gap-8 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <ReportPrintHeader reportTitle={t("accounting.tabs.balance_sheet")} dateRangeLabel={ranAt ?? undefined} />
          </div>

          {/* ── Assets (left column) ── */}
          <table className="w-full border-collapse text-sm">
            <FinancialSection
              label={t("accounting.bs.assets")}
              rows={r.assets}
              total={r.assets_total}
              totalLabel={t("accounting.bs.total_assets")}
              totalBorder="double"
            />
          </table>

          {/* ── Liabilities + Equity (right column) ── */}
          <table className="w-full border-collapse text-sm">
            <FinancialSection
              label={t("accounting.bs.liabilities")}
              rows={r.liabilities}
              total={r.liabilities_total}
              totalLabel={t("accounting.bs.total_liabilities")}
            />
            {/* Equity section — inline because it has the extra "Current Earnings" row */}
            <tbody>
              <tr>
                <td colSpan={3} className="pt-4 pb-1 font-semibold font-sans">
                  {t("accounting.bs.equity")}
                </td>
              </tr>
              {r.equity.map((row) => (
                <tr key={row.account_id}>
                  <td className="ps-4 py-0.5 font-mono text-xs text-muted-foreground w-20">
                    {row.account_code}
                  </td>
                  <td className="ps-2 py-0.5 text-muted-foreground">
                    <Link
                      href={`/accounting?tab=general-ledger&account=${row.account_id}`}
                      className="underline-offset-4 hover:underline"
                      title={t("accounting.tb.drill_down_hint")}
                    >
                      {row.account_name}
                    </Link>
                  </td>
                  <td className="py-0.5 text-end font-mono tabular-nums text-muted-foreground">
                    {formatCurrency(row.amount)}
                  </td>
                </tr>
              ))}
              {/* Current Earnings — auto-computed, no account id */}
              <tr>
                <td className="ps-4 py-0.5 font-mono text-xs text-muted-foreground w-20">—</td>
                <td className="ps-2 py-0.5 text-muted-foreground italic">{t("accounting.bs.current_earnings")}</td>
                <td className="py-0.5 text-end font-mono tabular-nums text-muted-foreground">
                  {formatCurrency(r.current_earnings)}
                </td>
              </tr>
              <tr className="border-t font-semibold">
                <td className="py-1 w-20" />
                <td className="py-1 font-sans">{t("accounting.bs.total_equity")}</td>
                <td className="py-1 text-end font-mono tabular-nums">{formatCurrency(r.equity_total)}</td>
              </tr>
              {/* Grand total: Liabilities + Equity */}
              <tr className="border-t-2 border-double font-bold text-base">
                <td className="py-2 w-20" />
                <td className="py-2 font-sans">{t("accounting.bs.total_liabilities_and_equity")}</td>
                <td className="py-2 text-end font-mono tabular-nums">
                  {formatCurrency(r.total_liabilities_and_equity)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </ReportView>
  );
}

function VatSummaryTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ from: string; to: string } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["vat-summary", companyId, ranAt?.from, ranAt?.to],
    queryFn: () => reportingApi.vatSummary(companyId, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });
  const r = reportQuery.data;
  const netPayable = r ? Number(r.net_vat_payable) : 0;

  return (
    <ReportView
      title={t("accounting.tabs.vat_summary")}
      filterArea={
        <>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.vat.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.vat.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
        </>
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo })}
      onPrint={r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/reporting/vat-summary",
            { date_from: ranAt.from, date_to: ranAt.to, lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      kpis={
        r
          ? [
              { label: t("accounting.vat.output_vat"), value: formatCurrency(r.output_vat) },
              { label: t("accounting.vat.input_vat"), value: formatCurrency(r.input_vat) },
              {
                label: netPayable >= 0 ? t("accounting.vat.net_vat_payable") : t("accounting.vat.net_vat_refundable"),
                value: formatCurrency(Math.abs(netPayable)),
              },
            ]
          : undefined
      }
    >
      {!r && <p className="text-sm text-muted-foreground">{t("accounting.vat.run_hint")}</p>}
      {r && (
        <div className="max-w-lg">
          <ReportPrintHeader
            reportTitle={t("accounting.tabs.vat_summary")}
            dateRangeLabel={ranAt ? `${ranAt.from} – ${ranAt.to}` : undefined}
          />
          <table className="w-full border-collapse">
            <tbody>
              <tr>
                <td className="py-1.5 font-sans">{t("accounting.vat.sales_subtotal")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.sales_subtotal)}</td>
              </tr>
              <tr>
                <td className="py-1.5 font-sans">{t("accounting.vat.output_vat")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.output_vat)}</td>
              </tr>
              <tr className="border-t font-semibold">
                <td className="py-1.5 font-sans">{t("accounting.vat.sales_total")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.sales_total)}</td>
              </tr>
            </tbody>
            <tbody>
              <tr>
                <td className="pt-4 py-1.5 font-sans">{t("accounting.vat.purchases_subtotal")}</td>
                <td className="pt-4 py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.purchases_subtotal)}</td>
              </tr>
              <tr>
                <td className="py-1.5 font-sans">{t("accounting.vat.input_vat")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.input_vat)}</td>
              </tr>
              <tr className="border-t font-semibold">
                <td className="py-1.5 font-sans">{t("accounting.vat.purchases_total")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.purchases_total)}</td>
              </tr>
            </tbody>
            <tbody>
              <tr className="border-t-2 border-double font-bold text-base">
                <td className="py-2 font-sans">
                  {netPayable >= 0 ? t("accounting.vat.net_vat_payable") : t("accounting.vat.net_vat_refundable")}
                </td>
                <td className="py-2 text-end font-mono tabular-nums">{formatCurrency(Math.abs(netPayable))}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </ReportView>
  );
}

function SubledgerLinesTable({ lines }: { lines: SubledgerLine[] }) {
  const { t, locale } = useI18n();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("accounting.sub.date")}</TableHead>
          <TableHead>{t("accounting.sub.reference")}</TableHead>
          <TableHead className="text-end">{t("accounting.sub.debit")}</TableHead>
          <TableHead className="text-end">{t("accounting.sub.credit")}</TableHead>
          <TableHead className="text-end">{t("accounting.sub.running_balance")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {lines.length === 0 && (
          <TableRow>
            <TableCell colSpan={5} className="text-center text-muted-foreground">
              {t("common.empty")}
            </TableCell>
          </TableRow>
        )}
        {lines.map((line, i) => {
          const href = sourceDocumentHref(line.document_type, line.document_id);
          return (
            <TableRow key={i}>
              <TableCell>{formatDate(line.date, locale)}</TableCell>
              <TableCell>
                {href ? (
                  <Link href={href} className="underline-offset-4 hover:underline">
                    {line.reference}
                  </Link>
                ) : (
                  line.reference
                )}
              </TableCell>
              <TableCell className="text-end font-mono">{formatCurrency(line.debit)}</TableCell>
              <TableCell className="text-end font-mono">{formatCurrency(line.credit)}</TableCell>
              <TableCell className="text-end font-mono">{formatCurrency(line.running_balance)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

function CustomerSubledgerTab({ initialPartnerId }: { initialPartnerId?: string }) {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  // Deep-link from a Partner Profile's Accounting tab ("smart action" per
  // the Unified Address Book bundle) — preselects and auto-runs the report
  // for that customer on first render instead of just landing on the right
  // tab. Read once via lazy useState initializers (not an effect) since
  // this only ever needs to apply once, on mount.
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [partnerId, setPartnerId] = useState(initialPartnerId ?? "");
  const [ranAt, setRanAt] = useState<{ partner: string; from: string; to: string } | null>(() =>
    initialPartnerId ? { partner: initialPartnerId, from: dateFrom, to: dateTo } : null
  );

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "customers"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { customersOnly: true }),
  });
  const reportQuery = useQuery({
    queryKey: ["customer-subledger", companyId, ranAt?.partner, ranAt?.from, ranAt?.to],
    queryFn: () => paymentsApi.customerSubledger(companyId, ranAt!.partner, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  return (
    <ReportView
      title={t("accounting.tabs.customer_subledger")}
      filterArea={
        <>
          <div className="w-64 space-y-1">
            <Label className="text-xs">{t("accounting.sub.select_customer")}</Label>
            <Select value={partnerId} onValueChange={(v) => setPartnerId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("accounting.sub.select_customer")}>
                  {(value: string) => partnersQuery.data?.find((p) => p.id === value)?.name ?? value}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {partnersQuery.data?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
        </>
      }
      onApply={partnerId ? () => setRanAt({ partner: partnerId, from: dateFrom, to: dateTo }) : undefined}
      onPrint={ranAt && reportQuery.data ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            `/api/v1/payments/subledger/customer/${ranAt.partner}`,
            { date_from: ranAt.from, date_to: ranAt.to, lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      kpis={
        ranAt && reportQuery.data
          ? [
              { label: t("accounting.sub.opening_balance"), value: formatCurrency(reportQuery.data.opening_balance) },
              { label: t("accounting.sub.closing_balance"), value: formatCurrency(reportQuery.data.closing_balance) },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.sub.select_partner_hint")}</p>}
      {ranAt && reportQuery.data && (
        <>
          <ReportPrintHeader
            reportTitle={t("accounting.sub.statement_title")}
            subtitle={reportQuery.data.partner_name}
            dateRangeLabel={`${reportQuery.data.date_from} – ${reportQuery.data.date_to}`}
          />
          <SubledgerLinesTable lines={reportQuery.data.lines} />
        </>
      )}
    </ReportView>
  );
}

function VendorSubledgerTab({ initialPartnerId }: { initialPartnerId?: string }) {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [partnerId, setPartnerId] = useState(initialPartnerId ?? "");
  const [ranAt, setRanAt] = useState<{ partner: string; from: string; to: string } | null>(() =>
    initialPartnerId ? { partner: initialPartnerId, from: dateFrom, to: dateTo } : null
  );

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "vendors"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });
  const reportQuery = useQuery({
    queryKey: ["vendor-subledger", companyId, ranAt?.partner, ranAt?.from, ranAt?.to],
    queryFn: () => paymentsApi.vendorSubledger(companyId, ranAt!.partner, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  return (
    <ReportView
      title={t("accounting.tabs.vendor_subledger")}
      filterArea={
        <>
          <div className="w-64 space-y-1">
            <Label className="text-xs">{t("accounting.sub.select_vendor")}</Label>
            <Select value={partnerId} onValueChange={(v) => setPartnerId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("accounting.sub.select_vendor")}>
                  {(value: string) => partnersQuery.data?.find((p) => p.id === value)?.name ?? value}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {partnersQuery.data?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
        </>
      }
      onApply={partnerId ? () => setRanAt({ partner: partnerId, from: dateFrom, to: dateTo }) : undefined}
      onPrint={ranAt && reportQuery.data ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            `/api/v1/payments/subledger/vendor/${ranAt.partner}`,
            { date_from: ranAt.from, date_to: ranAt.to, lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      kpis={
        ranAt && reportQuery.data
          ? [
              { label: t("accounting.sub.opening_balance"), value: formatCurrency(reportQuery.data.opening_balance) },
              { label: t("accounting.sub.closing_balance"), value: formatCurrency(reportQuery.data.closing_balance) },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.sub.select_partner_hint")}</p>}
      {ranAt && reportQuery.data && (
        <>
          <ReportPrintHeader
            reportTitle={t("accounting.sub.statement_title")}
            subtitle={reportQuery.data.partner_name}
            dateRangeLabel={`${reportQuery.data.date_from} – ${reportQuery.data.date_to}`}
          />
          <SubledgerLinesTable lines={reportQuery.data.lines} />
        </>
      )}
    </ReportView>
  );
}

function AgingTable({
  rows,
  partnerLabel,
  documentSourceTable,
}: {
  rows: AgingRow[];
  partnerLabel: string;
  /** Resolves each row's document number to a source-document link, where
   * that document type already has a real detail page (see
   * lib/source-document-links.ts) — sales_invoice and vendor_bill do. */
  documentSourceTable?: string;
}) {
  const { t, locale } = useI18n();
  // Owner-reported: no visible total meant the only way to check "does
  // Accounts Receivable in the Trial Balance match the sum of open
  // customer balances here" was to add up every row by hand. The
  // underlying figures already tie out exactly (verified directly against
  // Al-Mahmoud's ledger) — the actual gap was this report never showing
  // the number to compare against, matching the Trial Balance's own
  // totals row below.
  const total = rows.reduce((sum, r) => sum + Number(r.balance_due), 0);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{partnerLabel}</TableHead>
          <TableHead>{t("accounting.aging.document")}</TableHead>
          <TableHead>{t("accounting.aging.due_date")}</TableHead>
          <TableHead className="text-end">{t("accounting.aging.balance_due")}</TableHead>
          <TableHead>{t("accounting.aging.bucket")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.length === 0 && (
          <TableRow>
            <TableCell colSpan={5} className="text-center text-muted-foreground">
              {t("common.empty")}
            </TableCell>
          </TableRow>
        )}
        {rows.map((row, i) => {
          const href = documentSourceTable ? sourceDocumentHref(documentSourceTable, row.document_id) : null;
          return (
          <TableRow key={i}>
            <TableCell>{row.partner_name}</TableCell>
            <TableCell>
              {href ? (
                <Link href={href} className="underline-offset-4 hover:underline">
                  {row.number}
                </Link>
              ) : (
                row.number
              )}
            </TableCell>
            <TableCell>{formatDate(row.due_date, locale)}</TableCell>
            <TableCell className="text-end font-mono">{formatCurrency(row.balance_due)}</TableCell>
            <TableCell>
              <Badge variant={statusVariant(row.bucket)}>
                {t(`accounting.aging.bucket.${row.bucket}`)}
              </Badge>
            </TableCell>
          </TableRow>
          );
        })}
      </TableBody>
      {rows.length > 0 && (
        <TableFooter>
          <TableRow>
            <TableCell colSpan={3}>{t("accounting.aging.total")}</TableCell>
            <TableCell className="text-end font-mono">{formatCurrency(String(total))}</TableCell>
            <TableCell />
          </TableRow>
        </TableFooter>
      )}
    </Table>
  );
}

function ArAgingTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const [asOfDate, setAsOfDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<string | null>(null);

  const reportQuery = useQuery({
    queryKey: ["ar-aging", companyId, ranAt],
    queryFn: () => paymentsApi.arAging(companyId, ranAt!),
    enabled: !!ranAt,
  });

  return (
    <ReportView
      title={t("accounting.tabs.ar_aging")}
      filterArea={
        <div className="space-y-1">
          <Label className="text-xs">{t("accounting.aging.as_of_date")}</Label>
          <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-40" />
        </div>
      }
      onApply={() => setRanAt(asOfDate)}
      onPrint={ranAt && reportQuery.data ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers("/api/v1/payments/aging/ar", { as_of_date: ranAt, lang: locale }, companyId)
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!ranAt && !!reportQuery.data && reportQuery.data.rows.length === 0}
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.sub.select_partner_hint")}</p>}
      {ranAt && reportQuery.data && (
        <>
          <ReportPrintHeader reportTitle={t("accounting.tabs.ar_aging")} dateRangeLabel={reportQuery.data.as_of_date} />
          <AgingTable rows={reportQuery.data.rows} partnerLabel={t("accounting.aging.partner")} documentSourceTable="sales_invoice" />
        </>
      )}
    </ReportView>
  );
}

function ApAgingTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const [asOfDate, setAsOfDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<string | null>(null);

  const reportQuery = useQuery({
    queryKey: ["ap-aging", companyId, ranAt],
    queryFn: () => paymentsApi.apAging(companyId, ranAt!),
    enabled: !!ranAt,
  });

  return (
    <ReportView
      title={t("accounting.tabs.ap_aging")}
      filterArea={
        <div className="space-y-1">
          <Label className="text-xs">{t("accounting.aging.as_of_date")}</Label>
          <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-40" />
        </div>
      }
      onApply={() => setRanAt(asOfDate)}
      onPrint={ranAt && reportQuery.data ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers("/api/v1/payments/aging/ap", { as_of_date: ranAt, lang: locale }, companyId)
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!ranAt && !!reportQuery.data && reportQuery.data.rows.length === 0}
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.sub.select_partner_hint")}</p>}
      {ranAt && reportQuery.data && (
        <>
          <ReportPrintHeader reportTitle={t("accounting.tabs.ap_aging")} dateRangeLabel={reportQuery.data.as_of_date} />
          <AgingTable rows={reportQuery.data.rows} partnerLabel={t("accounting.aging.vendor")} documentSourceTable="vendor_bill" />
        </>
      )}
    </ReportView>
  );
}

export default function AccountingPage() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  // Base UI's Tabs.Panel fails to hide inactive panels once a second panel
  // mounts (its internal data-index tracking never resolves past -1 for
  // panels mounted after first render, so `hidden`/`data-hidden` never gets
  // set) — confirmed by inspecting the live DOM. Controlling the active tab
  // ourselves and gating each panel's content on it sidesteps the bug
  // regardless of its root cause.
  const urlTab = searchParams.get("tab");
  const [tab, setTab] = useState(() => urlTab ?? "accounts");
  // A drill-down link (e.g. Trial Balance row -> General Ledger) is a
  // same-route client-side navigation, so this component never remounts —
  // the useState initializer above only runs once and never sees a later
  // ?tab= value on its own. Tracking the last-observed URL value (same
  // derived-state-during-render pattern as EntityImage's src-change
  // handling) and only forcing a sync when THAT changes — rather than
  // whenever it merely differs from `tab` — is what makes this safe:
  // manually clicking a TabsTrigger doesn't touch the URL, so `urlTab`
  // stays constant and this deliberately leaves that local switch alone.
  const [lastUrlTab, setLastUrlTab] = useState(urlTab);
  if (urlTab && urlTab !== lastUrlTab) {
    setLastUrlTab(urlTab);
    setTab(urlTab);
  }
  const deepLinkPartnerId = searchParams.get("partner") ?? undefined;
  const deepLinkAccountId = searchParams.get("account") ?? undefined;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t("nav.accounting")}</h1>
      <Tabs value={tab} onValueChange={(v) => setTab(v as string)}>
        <TabsList>
          <TabsTrigger value="accounts">{t("accounting.tabs.accounts")}</TabsTrigger>
          <TabsTrigger value="journal-entries">{t("accounting.tabs.journal_entries")}</TabsTrigger>
          <TabsTrigger value="trial-balance">{t("accounting.tabs.trial_balance")}</TabsTrigger>
          <TabsTrigger value="general-ledger">{t("accounting.tabs.general_ledger")}</TabsTrigger>
          <TabsTrigger value="income-statement">{t("accounting.tabs.income_statement")}</TabsTrigger>
          <TabsTrigger value="balance-sheet">{t("accounting.tabs.balance_sheet")}</TabsTrigger>
          <TabsTrigger value="vat-summary">{t("accounting.tabs.vat_summary")}</TabsTrigger>
          <TabsTrigger value="customer-subledger">{t("accounting.tabs.customer_subledger")}</TabsTrigger>
          <TabsTrigger value="vendor-subledger">{t("accounting.tabs.vendor_subledger")}</TabsTrigger>
          <TabsTrigger value="ar-aging">{t("accounting.tabs.ar_aging")}</TabsTrigger>
          <TabsTrigger value="ap-aging">{t("accounting.tabs.ap_aging")}</TabsTrigger>
        </TabsList>
        <TabsContent value="accounts">{tab === "accounts" && <ChartOfAccountsTab />}</TabsContent>
        <TabsContent value="journal-entries">{tab === "journal-entries" && <JournalEntriesTab />}</TabsContent>
        <TabsContent value="trial-balance">{tab === "trial-balance" && <TrialBalanceTab />}</TabsContent>
        <TabsContent value="general-ledger">{tab === "general-ledger" && <GeneralLedgerTab initialAccountId={deepLinkAccountId} />}</TabsContent>
        <TabsContent value="income-statement">{tab === "income-statement" && <IncomeStatementTab />}</TabsContent>
        <TabsContent value="balance-sheet">{tab === "balance-sheet" && <BalanceSheetTab />}</TabsContent>
        <TabsContent value="vat-summary">{tab === "vat-summary" && <VatSummaryTab />}</TabsContent>
        <TabsContent value="customer-subledger">
          {tab === "customer-subledger" && <CustomerSubledgerTab initialPartnerId={deepLinkPartnerId} />}
        </TabsContent>
        <TabsContent value="vendor-subledger">
          {tab === "vendor-subledger" && <VendorSubledgerTab initialPartnerId={deepLinkPartnerId} />}
        </TabsContent>
        <TabsContent value="ar-aging">{tab === "ar-aging" && <ArAgingTab />}</TabsContent>
        <TabsContent value="ap-aging">{tab === "ap-aging" && <ApAgingTab />}</TabsContent>
      </Tabs>
    </div>
  );
}
