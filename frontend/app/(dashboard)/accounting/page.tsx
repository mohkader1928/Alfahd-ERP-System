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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";
import type { AgingRow, SubledgerLine } from "@/features/payments/api/types";
import { ApiError } from "@/lib/api-client";
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
        lines,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["journal-entries", companyId] });
      toastSuccess(t("toast.success_title"), t("accounting.je.save"));
      setReference("");
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

function TrialBalanceTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ from: string; to: string } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["trial-balance", companyId, ranAt?.from, ranAt?.to],
    queryFn: () => accountingApi.trialBalance(companyId, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  const totalDebit = reportQuery.data?.reduce((sum, r) => sum + Number(r.total_debit), 0) ?? 0;
  const totalCredit = reportQuery.data?.reduce((sum, r) => sum + Number(r.total_credit), 0) ?? 0;

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
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!ranAt && !reportQuery.isLoading && reportQuery.data?.length === 0}
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.sub.select_partner_hint")}</p>}
      {ranAt && reportQuery.data && (
        <>
          <ReportPrintHeader reportTitle={t("accounting.tabs.trial_balance")} dateRangeLabel={`${ranAt.from} – ${ranAt.to}`} />
          <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("accounting.accounts.code")}</TableHead>
              <TableHead>{t("accounting.accounts.name")}</TableHead>
              <TableHead className="text-end">{t("accounting.tb.total_debit")}</TableHead>
              <TableHead className="text-end">{t("accounting.tb.total_credit")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {reportQuery.data.map((row) => (
              <TableRow key={row.account_id}>
                <TableCell className="font-mono">{row.account_code}</TableCell>
                <TableCell>{row.account_name}</TableCell>
                <TableCell className="text-end">{formatCurrency(row.total_debit)}</TableCell>
                <TableCell className="text-end">{formatCurrency(row.total_credit)}</TableCell>
              </TableRow>
            ))}
            <TableRow className="font-semibold">
              <TableCell colSpan={2}>{t("accounting.tb.total")}</TableCell>
              <TableCell className="text-end">{formatCurrency(totalDebit)}</TableCell>
              <TableCell className="text-end">{formatCurrency(totalCredit)}</TableCell>
            </TableRow>
          </TableBody>
          </Table>
        </>
      )}
    </ReportView>
  );
}

function GeneralLedgerTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [accountId, setAccountId] = useState("");
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ account: string; from: string; to: string } | null>(null);

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

function IncomeStatementTab() {
  const { t } = useI18n();
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
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
    >
      {!r && <p className="text-sm text-muted-foreground">{t("accounting.gl.select_account_hint")}</p>}
      {r && (
        <div className="max-w-md space-y-1 font-mono text-sm">
          <ReportPrintHeader reportTitle={t("accounting.tabs.income_statement")} dateRangeLabel={ranAt ? `${ranAt.from} – ${ranAt.to}` : undefined} />
          <div className="flex justify-between">
            <span className="font-sans">{t("accounting.is.revenue")}</span>
            <span>{formatCurrency(r.revenue_total)}</span>
          </div>
          <div className="flex justify-between text-muted-foreground">
            <span className="font-sans">{t("accounting.is.cogs")}</span>
            <span>({formatCurrency(r.cogs_total)})</span>
          </div>
          <div className="flex justify-between border-t pt-1 font-semibold">
            <span className="font-sans">{t("accounting.is.gross_profit")}</span>
            <span>{formatCurrency(r.gross_profit)}</span>
          </div>
          <div className="flex justify-between text-muted-foreground">
            <span className="font-sans">{t("accounting.is.opex")}</span>
            <span>({formatCurrency(r.opex_total)})</span>
          </div>
          <div className="flex justify-between border-t pt-1 font-semibold">
            <span className="font-sans">{t("accounting.is.operating_income")}</span>
            <span>{formatCurrency(r.operating_income)}</span>
          </div>
          <div className="flex justify-between border-t-2 pt-1 text-base font-bold">
            <span className="font-sans">{t("accounting.is.net_income")}</span>
            <span>{formatCurrency(r.net_income)}</span>
          </div>
        </div>
      )}
    </ReportView>
  );
}

function BalanceSheetSection({
  title,
  totalLabel,
  rows,
  total,
}: {
  title: string;
  totalLabel: string;
  rows: { account_name: string; amount: string }[];
  total: string;
}) {
  return (
    <div className="space-y-1 font-mono text-sm">
      <p className="font-sans font-semibold">{title}</p>
      {rows.map((row, i) => (
        <div key={i} className="flex justify-between ps-4">
          <span className="font-sans text-muted-foreground">{row.account_name}</span>
          <span>{formatCurrency(row.amount)}</span>
        </div>
      ))}
      <div className="flex justify-between border-t pt-1 font-semibold">
        <span className="font-sans">{totalLabel}</span>
        <span>{formatCurrency(total)}</span>
      </div>
    </div>
  );
}

function BalanceSheetTab() {
  const { t } = useI18n();
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
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
    >
      {!r && <p className="text-sm text-muted-foreground">{t("accounting.gl.select_account_hint")}</p>}
      {r && (
        <div className="grid max-w-2xl grid-cols-1 gap-6 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <ReportPrintHeader reportTitle={t("accounting.tabs.balance_sheet")} dateRangeLabel={ranAt ?? undefined} />
          </div>
          <BalanceSheetSection
            title={t("accounting.bs.assets")}
            totalLabel={t("accounting.bs.total_assets")}
            rows={r.assets}
            total={r.assets_total}
          />
          <div className="space-y-4">
            <BalanceSheetSection
              title={t("accounting.bs.liabilities")}
              totalLabel={t("accounting.bs.total_liabilities")}
              rows={r.liabilities}
              total={r.liabilities_total}
            />
            <div className="space-y-1 font-mono text-sm">
              <p className="font-sans font-semibold">{t("accounting.bs.equity")}</p>
              {r.equity.map((row, i) => (
                <div key={i} className="flex justify-between ps-4">
                  <span className="font-sans text-muted-foreground">{row.account_name}</span>
                  <span>{formatCurrency(row.amount)}</span>
                </div>
              ))}
              <div className="flex justify-between ps-4">
                <span className="font-sans text-muted-foreground">{t("accounting.bs.current_earnings")}</span>
                <span>{formatCurrency(r.current_earnings)}</span>
              </div>
              <div className="flex justify-between border-t pt-1 font-semibold">
                <span className="font-sans">{t("accounting.bs.total_equity")}</span>
                <span>{formatCurrency(r.equity_total)}</span>
              </div>
            </div>
            <div className="flex justify-between border-t-2 pt-1 font-mono text-sm font-bold">
              <span className="font-sans">{t("accounting.bs.total_liabilities_and_equity")}</span>
              <span>{formatCurrency(r.total_liabilities_and_equity)}</span>
            </div>
          </div>
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
  const { t } = useI18n();
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
  const { t } = useI18n();
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
    </Table>
  );
}

function ArAgingTab() {
  const { t } = useI18n();
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
  const { t } = useI18n();
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
  const [tab, setTab] = useState(() => searchParams.get("tab") ?? "accounts");
  const deepLinkPartnerId = searchParams.get("partner") ?? undefined;
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
          <TabsTrigger value="customer-subledger">{t("accounting.tabs.customer_subledger")}</TabsTrigger>
          <TabsTrigger value="vendor-subledger">{t("accounting.tabs.vendor_subledger")}</TabsTrigger>
          <TabsTrigger value="ar-aging">{t("accounting.tabs.ar_aging")}</TabsTrigger>
          <TabsTrigger value="ap-aging">{t("accounting.tabs.ap_aging")}</TabsTrigger>
        </TabsList>
        <TabsContent value="accounts">{tab === "accounts" && <ChartOfAccountsTab />}</TabsContent>
        <TabsContent value="journal-entries">{tab === "journal-entries" && <JournalEntriesTab />}</TabsContent>
        <TabsContent value="trial-balance">{tab === "trial-balance" && <TrialBalanceTab />}</TabsContent>
        <TabsContent value="general-ledger">{tab === "general-ledger" && <GeneralLedgerTab />}</TabsContent>
        <TabsContent value="income-statement">{tab === "income-statement" && <IncomeStatementTab />}</TabsContent>
        <TabsContent value="balance-sheet">{tab === "balance-sheet" && <BalanceSheetTab />}</TabsContent>
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
