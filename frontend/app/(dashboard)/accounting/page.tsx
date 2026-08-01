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
import { ApiError } from "@/lib/api-client";

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
      setCode("");
      setName("");
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
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
      setReference("");
      setLines([
        { account_id: "", debit: "0", credit: "0" },
        { account_id: "", debit: "0", credit: "0" },
      ]);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
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
                  <Badge variant={e.status === "posted" ? "default" : "secondary"}>{e.status}</Badge>
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
                <TableCell className="text-end">{row.total_debit}</TableCell>
                <TableCell className="text-end">{row.total_credit}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
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
        </TabsList>
        <TabsContent value="accounts">{tab === "accounts" && <ChartOfAccountsTab />}</TabsContent>
        <TabsContent value="journal-entries">{tab === "journal-entries" && <JournalEntriesTab />}</TabsContent>
        <TabsContent value="trial-balance">{tab === "trial-balance" && <TrialBalanceTab />}</TabsContent>
      </Tabs>
    </div>
  );
}
