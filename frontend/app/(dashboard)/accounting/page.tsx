"use client";

import { useState } from "react";
import Link from "next/link";
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
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import type { JournalEntryLineIn } from "@/features/accounting/api/types";
import { identityApi } from "@/features/identity/api/client";
import { paymentsApi } from "@/features/payments/api/client";
import { formatCurrency } from "@/lib/format-currency";
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("accounting.tabs.accounts")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
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
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("accounting.accounts.code")}</TableHead>
              <TableHead>{t("accounting.accounts.name")}</TableHead>
              <TableHead>{t("accounting.accounts.active")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!accountsQuery.isLoading && accountsQuery.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {accountsQuery.data?.map((a) => (
              <TableRow key={a.id}>
                <TableCell className="font-mono">{a.code}</TableCell>
                <TableCell>{a.name}</TableCell>
                <TableCell>
                  <Badge variant={a.is_active ? "default" : "secondary"}>{String(a.is_active)}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function JournalEntriesTab() {
  const { t } = useI18n();
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("accounting.tabs.journal_entries")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-3 rounded-md border p-3">
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
              {totalDebit.toFixed(2)} / {totalCredit.toFixed(2)}
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
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("accounting.je.date")}</TableHead>
              <TableHead>{t("accounting.je.reference")}</TableHead>
              <TableHead>{t("accounting.je.status")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!entriesQuery.isLoading && entriesQuery.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {entriesQuery.data?.map((e) => (
              <TableRow key={e.id}>
                <TableCell>{e.entry_date}</TableCell>
                <TableCell>
                  <Link
                    href={`/accounting/journal-entries/${e.id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {e.reference ?? e.id.slice(0, 8)}
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant={statusVariant(e.status)}>{e.status}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("accounting.tabs.trial_balance")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.tb.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
          <Button size="sm" onClick={() => setRanAt({ from: dateFrom, to: dateTo })}>
            {t("accounting.tb.run")}
          </Button>
        </div>
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
            {ranAt && !reportQuery.isLoading && reportQuery.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {reportQuery.data?.map((row) => (
              <TableRow key={row.account_id}>
                <TableCell className="font-mono">{row.account_code}</TableCell>
                <TableCell>{row.account_name}</TableCell>
                <TableCell className="text-end">{formatCurrency(row.total_debit)}</TableCell>
                <TableCell className="text-end">{formatCurrency(row.total_credit)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function GeneralLedgerTab() {
  const { t } = useI18n();
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
    <Card>
      <CardHeader>
        <CardTitle>{t("accounting.tabs.general_ledger")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
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
          <Button
            size="sm"
            disabled={!accountId}
            onClick={() => setRanAt({ account: accountId, from: dateFrom, to: dateTo })}
          >
            {t("accounting.gl.run")}
          </Button>
        </div>

        {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.gl.select_account_hint")}</p>}

        {ranAt && reportQuery.data && (
          <>
            <div className="flex gap-6 text-sm">
              <span>
                {t("accounting.gl.opening_balance")}:{" "}
                <span className="font-mono">{formatCurrency(reportQuery.data.opening_balance)}</span>
              </span>
              <span>
                {t("accounting.gl.closing_balance")}:{" "}
                <span className="font-mono">{formatCurrency(reportQuery.data.closing_balance)}</span>
              </span>
            </div>
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
                {reportQuery.data.lines.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground">
                      {t("common.empty")}
                    </TableCell>
                  </TableRow>
                )}
                {reportQuery.data.lines.map((line, i) => {
                  const sourceHref = sourceDocumentHref(line.source_table, line.source_id);
                  const sourceLabelKey = sourceDocumentLabelKey(line.source_table);
                  return (
                    <TableRow key={i}>
                      <TableCell>{line.entry_date}</TableCell>
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
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <CardTitle>{t("accounting.tabs.income_statement")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.is.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.is.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
          <Button size="sm" onClick={() => setRanAt({ from: dateFrom, to: dateTo })}>
            {t("accounting.is.run")}
          </Button>
        </div>

        {r && (
          <div className="max-w-md space-y-1 font-mono text-sm">
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
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <CardTitle>{t("accounting.tabs.balance_sheet")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.bs.as_of_date")}</Label>
            <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-40" />
          </div>
          <Button size="sm" onClick={() => setRanAt(asOfDate)}>
            {t("accounting.bs.run")}
          </Button>
        </div>

        {r && (
          <div className="grid max-w-2xl grid-cols-1 gap-6 sm:grid-cols-2">
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
      </CardContent>
    </Card>
  );
}

function SubledgerLinesTable({ lines }: { lines: SubledgerLine[] }) {
  const { t } = useI18n();
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
              <TableCell>{line.date}</TableCell>
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

function CustomerSubledgerTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ partner: string; from: string; to: string } | null>(null);

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "customers"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { customersOnly: true }),
  });
  const companyQuery = useQuery({
    queryKey: ["company", companyId],
    queryFn: () => identityApi.getCompany(companyId),
  });
  const reportQuery = useQuery({
    queryKey: ["customer-subledger", companyId, ranAt?.partner, ranAt?.from, ranAt?.to],
    queryFn: () => paymentsApi.customerSubledger(companyId, ranAt!.partner, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          {t("accounting.tabs.customer_subledger")}
          {ranAt && reportQuery.data && (
            <Button variant="outline" size="sm" onClick={() => window.print()} className="print:hidden">
              {t("accounting.sub.print")}
            </Button>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2 print:hidden">
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
          <Button size="sm" disabled={!partnerId} onClick={() => setRanAt({ partner: partnerId, from: dateFrom, to: dateTo })}>
            {t("accounting.sub.run")}
          </Button>
        </div>

        {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.sub.select_partner_hint")}</p>}

        {ranAt && reportQuery.data && (
          <>
            <div className="hidden print:block">
              <p className="text-base font-semibold">{companyQuery.data?.legal_name}</p>
              <h2 className="text-lg font-semibold">{t("accounting.sub.statement_title")} — {reportQuery.data.partner_name}</h2>
              <p className="text-sm text-muted-foreground">
                {reportQuery.data.date_from} – {reportQuery.data.date_to}
              </p>
            </div>
            <div className="flex gap-6 text-sm">
              <span>
                {t("accounting.sub.opening_balance")}:{" "}
                <span className="font-mono">{formatCurrency(reportQuery.data.opening_balance)}</span>
              </span>
              <span>
                {t("accounting.sub.closing_balance")}:{" "}
                <span className="font-mono">{formatCurrency(reportQuery.data.closing_balance)}</span>
              </span>
            </div>
            <SubledgerLinesTable lines={reportQuery.data.lines} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function VendorSubledgerTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ partner: string; from: string; to: string } | null>(null);

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "vendors"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });
  const companyQuery = useQuery({
    queryKey: ["company", companyId],
    queryFn: () => identityApi.getCompany(companyId),
  });
  const reportQuery = useQuery({
    queryKey: ["vendor-subledger", companyId, ranAt?.partner, ranAt?.from, ranAt?.to],
    queryFn: () => paymentsApi.vendorSubledger(companyId, ranAt!.partner, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          {t("accounting.tabs.vendor_subledger")}
          {ranAt && reportQuery.data && (
            <Button variant="outline" size="sm" onClick={() => window.print()} className="print:hidden">
              {t("accounting.sub.print")}
            </Button>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2 print:hidden">
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
          <Button size="sm" disabled={!partnerId} onClick={() => setRanAt({ partner: partnerId, from: dateFrom, to: dateTo })}>
            {t("accounting.sub.run")}
          </Button>
        </div>

        {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.sub.select_partner_hint")}</p>}

        {ranAt && reportQuery.data && (
          <>
            <div className="hidden print:block">
              <p className="text-base font-semibold">{companyQuery.data?.legal_name}</p>
              <h2 className="text-lg font-semibold">{t("accounting.sub.statement_title")} — {reportQuery.data.partner_name}</h2>
              <p className="text-sm text-muted-foreground">
                {reportQuery.data.date_from} – {reportQuery.data.date_to}
              </p>
            </div>
            <div className="flex gap-6 text-sm">
              <span>
                {t("accounting.sub.opening_balance")}:{" "}
                <span className="font-mono">{formatCurrency(reportQuery.data.opening_balance)}</span>
              </span>
              <span>
                {t("accounting.sub.closing_balance")}:{" "}
                <span className="font-mono">{formatCurrency(reportQuery.data.closing_balance)}</span>
              </span>
            </div>
            <SubledgerLinesTable lines={reportQuery.data.lines} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function AgingTable({ rows, partnerLabel }: { rows: AgingRow[]; partnerLabel: string }) {
  const { t } = useI18n();
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
        {rows.map((row, i) => (
          <TableRow key={i}>
            <TableCell>{row.partner_name}</TableCell>
            <TableCell>{row.number}</TableCell>
            <TableCell>{row.due_date}</TableCell>
            <TableCell className="text-end font-mono">{formatCurrency(row.balance_due)}</TableCell>
            <TableCell>
              <Badge variant={statusVariant(row.bucket)}>
                {t(`accounting.aging.bucket.${row.bucket}`)}
              </Badge>
            </TableCell>
          </TableRow>
        ))}
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
    <Card>
      <CardHeader>
        <CardTitle>{t("accounting.tabs.ar_aging")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.aging.as_of_date")}</Label>
            <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-40" />
          </div>
          <Button size="sm" onClick={() => setRanAt(asOfDate)}>
            {t("accounting.aging.run")}
          </Button>
        </div>
        {reportQuery.data && <AgingTable rows={reportQuery.data.rows} partnerLabel={t("accounting.aging.partner")} />}
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <CardTitle>{t("accounting.tabs.ap_aging")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.aging.as_of_date")}</Label>
            <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-40" />
          </div>
          <Button size="sm" onClick={() => setRanAt(asOfDate)}>
            {t("accounting.aging.run")}
          </Button>
        </div>
        {reportQuery.data && <AgingTable rows={reportQuery.data.rows} partnerLabel={t("accounting.aging.vendor")} />}
      </CardContent>
    </Card>
  );
}

export default function AccountingPage() {
  const { t } = useI18n();
  // Base UI's Tabs.Panel fails to hide inactive panels once a second panel
  // mounts (its internal data-index tracking never resolves past -1 for
  // panels mounted after first render, so `hidden`/`data-hidden` never gets
  // set) — confirmed by inspecting the live DOM. Controlling the active tab
  // ourselves and gating each panel's content on it sidesteps the bug
  // regardless of its root cause.
  const [tab, setTab] = useState("accounts");
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
          {tab === "customer-subledger" && <CustomerSubledgerTab />}
        </TabsContent>
        <TabsContent value="vendor-subledger">
          {tab === "vendor-subledger" && <VendorSubledgerTab />}
        </TabsContent>
        <TabsContent value="ar-aging">{tab === "ar-aging" && <ArAgingTab />}</TabsContent>
        <TabsContent value="ap-aging">{tab === "ap-aging" && <ApAgingTab />}</TabsContent>
      </Tabs>
    </div>
  );
}
