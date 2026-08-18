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
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { Can } from "@/components/erp/permissions/can";
import { ConfirmDialog } from "@/components/erp/states/confirm-dialog";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import type {
  Account,
  CostCenter,
  FiscalPeriod,
  JournalEntry,
  JournalEntryLineIn,
} from "@/features/accounting/api/types";
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

const MAX_ACCOUNT_LEVEL = 4;

// Owner-requested follow-up to P0-4: Trial Balance / Income Statement /
// Balance Sheet all group figures by account, so all three can offer the
// same "how deep into the hierarchy" choice. MAX_ACCOUNT_LEVEL (4) means
// "no rollup" -- every posting account shows on its own, identical to
// what these reports already did before this control existed.
function DetailLevelSelect({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const { t } = useI18n();
  return (
    <div className="space-y-1">
      <Label className="text-xs">{t("accounting.reports.detail_level")}</Label>
      <Select value={String(value)} onValueChange={(v) => onChange(Number(v ?? MAX_ACCOUNT_LEVEL))}>
        <SelectTrigger className="w-40">
          <SelectValue>{(v: string) => t(`accounting.reports.detail_level_${v}`)}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {[1, 2, 3, MAX_ACCOUNT_LEVEL].map((level) => (
            <SelectItem key={level} value={String(level)}>
              {t(`accounting.reports.detail_level_${level}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function AccountFormFields({
  code,
  setCode,
  name,
  setName,
  accountTypeCode,
  setAccountTypeCode,
  parentId,
  setParentId,
  isGroup,
  setIsGroup,
  isCashEquivalent,
  setIsCashEquivalent,
  parentOptions,
  excludeId,
  showType = true,
}: {
  code: string;
  setCode: (v: string) => void;
  name: string;
  setName: (v: string) => void;
  accountTypeCode: string;
  setAccountTypeCode: (v: string) => void;
  parentId: string;
  setParentId: (v: string) => void;
  isGroup: boolean;
  setIsGroup: (v: boolean) => void;
  isCashEquivalent: boolean;
  setIsCashEquivalent: (v: boolean) => void;
  parentOptions: Account[];
  excludeId?: string;
  /** Account type is fixed at creation (changing it after transactions
   * exist would misclassify every historical posting in reports) and
   * AccountOut doesn't even expose the current type to prefill from --
   * hidden entirely in edit mode rather than shown incorrectly. */
  showType?: boolean;
}) {
  const { t } = useI18n();
  // A parent must have room for at least one more level below it, and an
  // account can't become its own (grand-)parent.
  const eligibleParents = parentOptions.filter((a) => a.level < MAX_ACCOUNT_LEVEL && a.id !== excludeId);

  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="space-y-1">
        <Label className="text-xs">{t("accounting.accounts.code")}</Label>
        <Input value={code} onChange={(e) => setCode(e.target.value)} className="w-28" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">{t("accounting.accounts.name")}</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
      </div>
      {showType && (
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
      )}
      <div className="space-y-1">
        <Label className="text-xs">{t("accounting.accounts.parent")}</Label>
        <Select value={parentId || "__root__"} onValueChange={(v) => setParentId(v === "__root__" ? "" : (v ?? ""))}>
          <SelectTrigger className="w-56">
            <SelectValue placeholder={t("accounting.accounts.parent_none")}>
              {(value: string) => {
                if (value === "__root__") return t("accounting.accounts.parent_none");
                const p = parentOptions.find((a) => a.id === value);
                return p ? `${p.code} — ${p.name}` : value;
              }}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__root__">{t("accounting.accounts.parent_none")}</SelectItem>
            {eligibleParents.map((a) => (
              <SelectItem key={a.id} value={a.id}>
                {"— ".repeat(a.level - 1)}
                {a.code} — {a.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <label className="flex items-center gap-2 pb-1.5 text-sm">
        <input type="checkbox" checked={isGroup} onChange={(e) => setIsGroup(e.target.checked)} />
        {t("accounting.accounts.is_group")}
      </label>
      <label className="flex items-center gap-2 pb-1.5 text-sm">
        <input
          type="checkbox"
          checked={isCashEquivalent}
          onChange={(e) => setIsCashEquivalent(e.target.checked)}
        />
        {t("accounting.accounts.is_cash_equivalent")}
      </label>
    </div>
  );
}

function ChartOfAccountsTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [accountTypeCode, setAccountTypeCode] = useState<string>("asset");
  const [parentId, setParentId] = useState("");
  const [isGroup, setIsGroup] = useState(false);
  const [isCashEquivalent, setIsCashEquivalent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Account | null>(null);
  const [editCode, setEditCode] = useState("");
  const [editName, setEditName] = useState("");
  const [editTypeCode, setEditTypeCode] = useState("asset");
  const [editParentId, setEditParentId] = useState("");
  const [editIsGroup, setEditIsGroup] = useState(false);
  const [editIsCashEquivalent, setEditIsCashEquivalent] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [deleting, setDeleting] = useState<Account | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["accounts", companyId],
    queryFn: () => accountingApi.listAccounts(companyId),
  });
  const accounts = accountsQuery.data ?? [];
  // Deepest-first ordering by level, then code within a level — reads as a
  // hierarchy at a glance without building a real tree widget for what's
  // still a fairly shallow (max 4 levels) structure.
  const sortedAccounts = [...accounts].sort((a, b) => a.code.localeCompare(b.code));

  const createMutation = useMutation({
    mutationFn: () =>
      accountingApi.createAccount(companyId, {
        code,
        name,
        account_type_code: accountTypeCode,
        parent_id: parentId || null,
        is_group: isGroup,
        is_cash_equivalent: isCashEquivalent,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts", companyId] });
      toastSuccess(t("toast.success_title"), name);
      setCode("");
      setName("");
      setParentId("");
      setIsGroup(false);
      setIsCashEquivalent(false);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      accountingApi.updateAccount(companyId, editing!.id, {
        code: editCode,
        name: editName,
        parent_id: editParentId || null,
        parent_id_set: true,
        is_group: editIsGroup,
        is_cash_equivalent: editIsCashEquivalent,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts", companyId] });
      toastSuccess(t("toast.success_title"), editName);
      setEditing(null);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setEditError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => accountingApi.deleteAccount(companyId, deleting!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts", companyId] });
      toastSuccess(t("toast.success_title"), t("accounting.accounts.delete"));
      setDeleting(null);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setDeleteError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  function openEdit(account: Account) {
    setEditing(account);
    setEditCode(account.code);
    setEditName(account.name);
    setEditTypeCode("asset"); // type isn't surfaced on AccountOut yet; left as-is unless changed
    setEditParentId(account.parent_id ?? "");
    setEditIsGroup(account.is_group);
    setEditIsCashEquivalent(account.is_cash_equivalent);
    setEditError(null);
  }

  const columns: ERPColumn<Account>[] = [
    { key: "code", header: t("accounting.accounts.code"), sortable: true, sortValue: (r) => r.code, render: (r) => <span className="font-mono">{r.code}</span> },
    {
      key: "name",
      header: t("accounting.accounts.name"),
      sortable: true,
      sortValue: (r) => r.name,
      render: (r) => <span style={{ paddingInlineStart: `${(r.level - 1) * 1.25}rem` }}>{r.name}</span>,
    },
    { key: "name_ar", header: t("master_data.partners.name_ar"), render: (r) => r.name_ar ?? "—" },
    {
      key: "level",
      header: t("accounting.accounts.level"),
      align: "end",
      sortable: true,
      sortValue: (r) => r.level,
      render: (r) => r.level,
    },
    {
      key: "is_group",
      header: t("accounting.accounts.is_group"),
      render: (r) => (
        <Badge variant={r.is_group ? "warning" : "outline"}>
          {r.is_group ? t("accounting.accounts.group") : t("accounting.accounts.posting")}
        </Badge>
      ),
    },
    {
      key: "is_active",
      header: t("accounting.accounts.active"),
      render: (r) => <Badge variant={r.is_active ? "default" : "secondary"}>{r.is_active ? t("common.active") : t("common.inactive")}</Badge>,
    },
    {
      key: "is_cash_equivalent",
      header: t("accounting.accounts.is_cash_equivalent"),
      render: (r) => (r.is_cash_equivalent ? <Badge variant="default">{t("common.yes")}</Badge> : "—"),
    },
    {
      key: "actions",
      header: "",
      render: (r) => (
        <Can permission="accounting.chart_of_accounts.manage">
          <div className="flex justify-end gap-1">
            <Button size="sm" variant="ghost" onClick={() => openEdit(r)}>
              {t("common.edit")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="text-destructive"
              onClick={() => {
                setDeleting(r);
                setDeleteError(null);
              }}
            >
              {t("common.delete")}
            </Button>
          </div>
        </Can>
      ),
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
            <AccountFormFields
              code={code}
              setCode={setCode}
              name={name}
              setName={setName}
              accountTypeCode={accountTypeCode}
              setAccountTypeCode={setAccountTypeCode}
              parentId={parentId}
              setParentId={setParentId}
              isGroup={isGroup}
              setIsGroup={setIsGroup}
              isCashEquivalent={isCashEquivalent}
              setIsCashEquivalent={setIsCashEquivalent}
              parentOptions={accounts}
            />
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
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </Can>
      <ERPListView
        title={t("accounting.tabs.accounts")}
        columns={columns}
        rows={sortedAccounts}
        rowKey={(r) => r.id}
        isLoading={accountsQuery.isLoading}
        isError={accountsQuery.isError}
        onRetry={() => accountsQuery.refetch()}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["accounts", companyId] })}
        searchText={(r) => `${r.code} ${r.name} ${r.name_ar ?? ""}`}
        searchPlaceholder={t("list.search_placeholder")}
        emptyDescription={t("common.empty")}
      />

      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("accounting.accounts.edit_title")}</DialogTitle>
          </DialogHeader>
          <AccountFormFields
            code={editCode}
            setCode={setEditCode}
            name={editName}
            setName={setEditName}
            accountTypeCode={editTypeCode}
            setAccountTypeCode={setEditTypeCode}
            parentId={editParentId}
            setParentId={setEditParentId}
            isGroup={editIsGroup}
            setIsGroup={setEditIsGroup}
            isCashEquivalent={editIsCashEquivalent}
            setIsCashEquivalent={setEditIsCashEquivalent}
            parentOptions={accounts}
            excludeId={editing?.id}
            showType={false}
          />
          {editError && <p className="text-sm text-destructive">{editError}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              disabled={!editCode || !editName || updateMutation.isPending}
              onClick={() => {
                setEditError(null);
                updateMutation.mutate();
              }}
            >
              {updateMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("accounting.accounts.delete_confirm_title")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t("accounting.accounts.delete_confirm_body")} {deleting?.code} — {deleting?.name}
          </p>
          {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)}>
              {t("common.cancel")}
            </Button>
            <Button variant="destructive" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate()}>
              {deleteMutation.isPending ? t("common.loading") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
  const costCentersQuery = useQuery({
    queryKey: ["cost-centers", companyId],
    queryFn: () => accountingApi.listCostCenters(companyId),
  });
  const activeCostCenters = costCentersQuery.data?.filter((c) => c.is_active) ?? [];
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
            <div className="space-y-3">
              {lines.map((line, index) => (
                <div key={index} className="space-y-1.5 border-b pb-3 last:border-b-0 last:pb-0">
                <div className="flex items-end gap-2">
                  <div className="flex-1 space-y-1">
                    <Label className="text-xs">{t("accounting.je.account")}</Label>
                    <Select
                      key={`account-${index}`}
                      value={line.account_id}
                      onValueChange={(v) => updateLine(index, { account_id: v ?? "" })}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t("accounting.je.account")}>
                          {(value: string) => {
                            const acc = accountsQuery.data?.find((a) => a.id === value);
                            return acc ? `${acc.code} — ${acc.name}` : value;
                          }}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {/* P0-4: a group/header account (has sub-accounts) can never
                            be posted to directly -- filtered out here so the backend's
                            422 rejection is a defense-in-depth backstop, not the first
                            time the user learns about it. */}
                        {accountsQuery.data
                          ?.filter((a) => !a.is_group)
                          .map((a) => (
                            <SelectItem key={a.id} value={a.id}>
                              {a.code} — {a.name}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="w-48 space-y-1">
                    <Label className="text-xs">{t("accounting.je.cost_center")}</Label>
                    <Select
                      key={`cost-center-${index}`}
                      value={line.cost_center_id ?? ""}
                      onValueChange={(v) => updateLine(index, { cost_center_id: v || null })}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t("accounting.je.cost_center_none")}>
                          {(value: string) =>
                            value ? (activeCostCenters.find((c) => c.id === value)?.name ?? value) : t("accounting.je.cost_center_none")
                          }
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="">{t("accounting.je.cost_center_none")}</SelectItem>
                        {activeCostCenters.map((c) => (
                          <SelectItem key={c.id} value={c.id}>
                            {c.name}
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
                <div className="space-y-1">
                  <Label className="text-xs">{t("accounting.je.line_notes")}</Label>
                  <Input
                    value={line.description ?? ""}
                    onChange={(e) => updateLine(index, { description: e.target.value || undefined })}
                    placeholder={t("accounting.je.line_notes_placeholder")}
                  />
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
  const [detailLevel, setDetailLevel] = useState(MAX_ACCOUNT_LEVEL);
  const [ranAt, setRanAt] = useState<{ from: string; to: string; level: number } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["trial-balance", companyId, ranAt?.from, ranAt?.to, ranAt?.level],
    queryFn: () => accountingApi.trialBalance(companyId, ranAt!.from, ranAt!.to, ranAt!.level),
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
          <DetailLevelSelect value={detailLevel} onChange={setDetailLevel} />
        </>
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo, level: detailLevel })}
      onPrint={ranAt && reportQuery.data ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/accounting/reports/trial-balance",
            { date_from: ranAt.from, date_to: ranAt.to, detail_level: String(ranAt.level), lang: locale },
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
                      {/* A rolled-up row's account_id is its ancestor, which
                          (being a group account) was never itself postable --
                          its own General Ledger would just be empty. Only
                          link through at full detail, where every row is
                          still its own real posting account. */}
                      {ranAt?.level === MAX_ACCOUNT_LEVEL ? (
                        <Link
                          href={`/accounting?tab=general-ledger&account=${row.account_id}`}
                          className="underline-offset-4 hover:underline"
                          title={t("accounting.tb.drill_down_hint")}
                        >
                          {row.account_name}
                        </Link>
                      ) : (
                        row.account_name
                      )}
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

/** Shared filter: "All cost centers" (empty value) plus every active cost
 * center, reused by General Ledger, Income Statement, and the dedicated
 * Cost Center Report tab. */
function CostCenterFilterSelect({
  value,
  onChange,
  costCenters,
}: {
  value: string;
  onChange: (v: string) => void;
  costCenters: CostCenter[];
}) {
  const { t } = useI18n();
  return (
    <div className="w-56 space-y-1">
      <Label className="text-xs">{t("accounting.gl.cost_center")}</Label>
      <Select value={value} onValueChange={(v) => onChange(v ?? "")}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder={t("accounting.gl.cost_center_all")}>
            {(v: string) => {
              if (!v) return t("accounting.gl.cost_center_all");
              return costCenters.find((c) => c.id === v)?.name ?? v;
            }}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="">{t("accounting.gl.cost_center_all")}</SelectItem>
          {costCenters.map((c) => (
            <SelectItem key={c.id} value={c.id}>
              {c.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function GeneralLedgerTab({ initialAccountId }: { initialAccountId?: string }) {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [accountId, setAccountId] = useState(initialAccountId ?? "");
  const [costCenterId, setCostCenterId] = useState("");
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ account: string; from: string; to: string; costCenter: string } | null>(() =>
    initialAccountId
      ? { account: initialAccountId, from: new Date().toISOString().slice(0, 8) + "01", to: new Date().toISOString().slice(0, 10), costCenter: "" }
      : null
  );
  // Same class of bug as Customer/Vendor Subledger below: drilling into a
  // different account from the Chart of Accounts while this tab is
  // already mounted (same route, only the `account` query param changes)
  // silently kept showing the first account's ledger, since the lazy
  // useState initializers above only fire on the very first mount.
  const [syncedAccountId, setSyncedAccountId] = useState(initialAccountId);
  if (initialAccountId !== syncedAccountId) {
    setAccountId(initialAccountId ?? "");
    setRanAt(initialAccountId ? { account: initialAccountId, from: dateFrom, to: dateTo, costCenter: "" } : null);
    setSyncedAccountId(initialAccountId);
  }

  const accountsQuery = useQuery({
    queryKey: ["accounts", companyId],
    queryFn: () => accountingApi.listAccounts(companyId),
  });
  const costCentersQuery = useQuery({
    queryKey: ["cost-centers", companyId],
    queryFn: () => accountingApi.listCostCenters(companyId),
  });
  const reportQuery = useQuery({
    queryKey: ["general-ledger", companyId, ranAt?.account, ranAt?.from, ranAt?.to, ranAt?.costCenter],
    queryFn: () =>
      accountingApi.generalLedger(companyId, ranAt!.account, ranAt!.from, ranAt!.to, ranAt!.costCenter || undefined),
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
          <CostCenterFilterSelect
            value={costCenterId}
            onChange={setCostCenterId}
            costCenters={costCentersQuery.data ?? []}
          />
        </>
      }
      onApply={
        accountId ? () => setRanAt({ account: accountId, from: dateFrom, to: dateTo, costCenter: costCenterId }) : undefined
      }
      onPrint={ranAt && reportQuery.data ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/accounting/reports/general-ledger",
            {
              account_id: ranAt.account,
              date_from: ranAt.from,
              date_to: ranAt.to,
              cost_center_id: ranAt.costCenter || undefined,
              lang: locale,
            },
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
              <TableHead>{t("accounting.gl.cost_center")}</TableHead>
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
                  <TableCell className="text-muted-foreground">{line.cost_center_name ?? "—"}</TableCell>
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
  linkAccounts = true,
}: {
  label: string;
  rows: { account_id: string; account_code: string; account_name: string; amount: string }[];
  total: string;
  totalLabel: string;
  sign?: 1 | -1;
  totalBorder?: "single" | "double";
  /** False while a detail-level rollup is active: a rolled-up row's
   * account_id is its ancestor, a group account that (by definition) was
   * never itself postable -- its own General Ledger would just be empty. */
  linkAccounts?: boolean;
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
              {linkAccounts ? (
                <Link
                  href={`/accounting?tab=general-ledger&account=${row.account_id}`}
                  className="underline-offset-4 hover:underline"
                  title={t("accounting.tb.drill_down_hint")}
                >
                  {row.account_name}
                </Link>
              ) : (
                row.account_name
              )}
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
  const [detailLevel, setDetailLevel] = useState(MAX_ACCOUNT_LEVEL);
  const [costCenterId, setCostCenterId] = useState("");
  const [ranAt, setRanAt] = useState<{ from: string; to: string; level: number; costCenter: string } | null>(null);

  const costCentersQuery = useQuery({
    queryKey: ["cost-centers", companyId],
    queryFn: () => accountingApi.listCostCenters(companyId),
  });
  const reportQuery = useQuery({
    queryKey: ["income-statement", companyId, ranAt?.from, ranAt?.to, ranAt?.level, ranAt?.costCenter],
    queryFn: () =>
      accountingApi.incomeStatement(companyId, ranAt!.from, ranAt!.to, ranAt!.level, ranAt!.costCenter || undefined),
    enabled: !!ranAt,
  });
  const r = reportQuery.data;
  const fullDetail = ranAt?.level === MAX_ACCOUNT_LEVEL;

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
          <DetailLevelSelect value={detailLevel} onChange={setDetailLevel} />
          <CostCenterFilterSelect
            value={costCenterId}
            onChange={setCostCenterId}
            costCenters={costCentersQuery.data ?? []}
          />
        </>
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo, level: detailLevel, costCenter: costCenterId })}
      onPrint={r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/accounting/reports/income-statement",
            {
              date_from: ranAt.from,
              date_to: ranAt.to,
              detail_level: String(ranAt.level),
              cost_center_id: ranAt.costCenter || undefined,
              lang: locale,
            },
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
              linkAccounts={fullDetail}
            />
            {/* COGS — shown as a deduction (negated for display) */}
            <FinancialSection
              label={t("accounting.is.cogs")}
              rows={r.cogs_accounts}
              total={r.cogs_total}
              totalLabel={t("accounting.is.total_cogs")}
              sign={-1}
              linkAccounts={fullDetail}
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
              linkAccounts={fullDetail}
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

function CashFlowTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ from: string; to: string } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["cash-flow", companyId, ranAt?.from, ranAt?.to],
    queryFn: () => accountingApi.cashFlowStatement(companyId, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });
  const r = reportQuery.data;
  const hasGap = r && Number(r.reconciliation_difference) !== 0;

  return (
    <ReportView
      title={t("accounting.tabs.cash_flow")}
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
      kpis={
        r
          ? [
              { label: t("accounting.cf.net_change"), value: formatCurrency(r.net_change_in_cash) },
              { label: t("accounting.cf.closing_cash"), value: formatCurrency(r.closing_cash) },
            ]
          : undefined
      }
    >
      {!r && <p className="text-sm text-muted-foreground">{t("accounting.gl.select_account_hint")}</p>}
      {r && (
        <div className="max-w-lg">
          <ReportPrintHeader
            reportTitle={t("accounting.tabs.cash_flow")}
            dateRangeLabel={ranAt ? `${ranAt.from} – ${ranAt.to}` : undefined}
          />
          {hasGap && (
            <p className="mb-3 rounded-md bg-amber-500/15 px-3 py-2 text-sm text-amber-700 dark:bg-amber-500/20 dark:text-amber-400 print:hidden">
              {t("accounting.cf.reconciliation_gap")}: {formatCurrency(r.reconciliation_difference)}
            </p>
          )}
          <table className="w-full border-collapse">
            {/* Operating Activities */}
            <tbody>
              <tr>
                <td colSpan={3} className="pt-4 pb-1 font-semibold text-sm font-sans">
                  {t("accounting.cf.operating")}
                </td>
              </tr>
              <tr>
                <td className="ps-4 py-0.5 w-20" />
                <td className="ps-2 py-0.5 text-sm text-muted-foreground">{t("accounting.cf.net_income")}</td>
                <td className="py-0.5 text-end font-mono text-sm tabular-nums text-muted-foreground">
                  {formatCurrency(r.net_income)}
                </td>
              </tr>
              <tr>
                <td className="ps-4 py-0.5 w-20" />
                <td className="ps-2 py-0.5 text-sm text-muted-foreground">{t("accounting.cf.depreciation")}</td>
                <td className="py-0.5 text-end font-mono text-sm tabular-nums text-muted-foreground">
                  {formatCurrency(r.depreciation_addback)}
                </td>
              </tr>
            </tbody>
            <FinancialSection
              label={t("accounting.cf.working_capital")}
              rows={r.working_capital_lines}
              total={r.working_capital_total}
              totalLabel={t("accounting.cf.working_capital_total")}
              linkAccounts
            />
            <tbody>
              <tr className="border-t font-semibold">
                <td className="py-1.5 w-20" />
                <td className="py-1.5 font-sans">{t("accounting.cf.operating_total")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.operating_total)}</td>
              </tr>
            </tbody>
            {/* Investing Activities */}
            <FinancialSection
              label={t("accounting.cf.investing")}
              rows={r.investing_lines}
              total={r.investing_total}
              totalLabel={t("accounting.cf.investing_total")}
              linkAccounts
            />
            {/* Financing Activities */}
            <FinancialSection
              label={t("accounting.cf.financing")}
              rows={r.financing_lines}
              total={r.financing_total}
              totalLabel={t("accounting.cf.financing_total")}
              linkAccounts
            />
            {/* Net change + opening + closing */}
            <tbody>
              <tr className="border-t-2 font-bold">
                <td className="py-1.5 w-20" />
                <td className="py-1.5 font-sans">{t("accounting.cf.net_change")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.net_change_in_cash)}</td>
              </tr>
              <tr>
                <td className="py-1.5 w-20" />
                <td className="py-1.5 font-sans">{t("accounting.cf.opening_cash")}</td>
                <td className="py-1.5 text-end font-mono tabular-nums">{formatCurrency(r.opening_cash)}</td>
              </tr>
              <tr className="border-t-2 border-double font-bold text-base">
                <td className="py-2 w-20" />
                <td className="py-2 font-sans">{t("accounting.cf.closing_cash")}</td>
                <td className="py-2 text-end font-mono tabular-nums">{formatCurrency(r.closing_cash)}</td>
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
  const [detailLevel, setDetailLevel] = useState(MAX_ACCOUNT_LEVEL);
  const [ranAt, setRanAt] = useState<{ date: string; level: number } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["balance-sheet", companyId, ranAt?.date, ranAt?.level],
    queryFn: () => accountingApi.balanceSheet(companyId, ranAt!.date, ranAt!.level),
    enabled: !!ranAt,
  });
  const r = reportQuery.data;
  const fullDetail = ranAt?.level === MAX_ACCOUNT_LEVEL;

  return (
    <ReportView
      title={t("accounting.tabs.balance_sheet")}
      filterArea={
        <>
          <div className="space-y-1">
            <Label className="text-xs">{t("accounting.bs.as_of_date")}</Label>
            <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-40" />
          </div>
          <DetailLevelSelect value={detailLevel} onChange={setDetailLevel} />
        </>
      }
      onApply={() => setRanAt({ date: asOfDate, level: detailLevel })}
      onPrint={r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/accounting/reports/balance-sheet",
            { as_of_date: ranAt.date, detail_level: String(ranAt.level), lang: locale },
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
            <ReportPrintHeader reportTitle={t("accounting.tabs.balance_sheet")} dateRangeLabel={ranAt?.date} />
          </div>

          {/* ── Assets (left column) ── */}
          <table className="w-full border-collapse text-sm">
            <FinancialSection
              label={t("accounting.bs.assets")}
              rows={r.assets}
              total={r.assets_total}
              totalLabel={t("accounting.bs.total_assets")}
              totalBorder="double"
              linkAccounts={fullDetail}
            />
          </table>

          {/* ── Liabilities + Equity (right column) ── */}
          <table className="w-full border-collapse text-sm">
            <FinancialSection
              label={t("accounting.bs.liabilities")}
              rows={r.liabilities}
              total={r.liabilities_total}
              totalLabel={t("accounting.bs.total_liabilities")}
              linkAccounts={fullDetail}
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
                    {fullDetail ? (
                      <Link
                        href={`/accounting?tab=general-ledger&account=${row.account_id}`}
                        className="underline-offset-4 hover:underline"
                        title={t("accounting.tb.drill_down_hint")}
                      >
                        {row.account_name}
                      </Link>
                    ) : (
                      row.account_name
                    )}
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
  // tab.
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [partnerId, setPartnerId] = useState(initialPartnerId ?? "");
  const [ranAt, setRanAt] = useState<{ partner: string; from: string; to: string } | null>(() =>
    initialPartnerId ? { partner: initialPartnerId, from: dateFrom, to: dateTo } : null
  );
  // Owner-reported bug: clicking "View customer account" from one Partner
  // Profile, then from a *different* Partner Profile, kept showing the
  // first customer's statement — this tab stays mounted across both
  // deep-links (same `/accounting?tab=customer-subledger` route, only the
  // `partner` query param changes), so the lazy useState initializers
  // above only ever fired once, on the very first mount, and silently
  // never re-synced to the new partner. Comparing the incoming prop
  // against what was last synced (during render, not an effect) is what
  // actually re-triggers on every subsequent deep-link.
  const [syncedPartnerId, setSyncedPartnerId] = useState(initialPartnerId);
  if (initialPartnerId !== syncedPartnerId) {
    setPartnerId(initialPartnerId ?? "");
    setRanAt(initialPartnerId ? { partner: initialPartnerId, from: dateFrom, to: dateTo } : null);
    setSyncedPartnerId(initialPartnerId);
  }

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
  // Owner-reported bug (PO-000033): "View vendor account" from one vendor's
  // Partner Profile, then from a different vendor's, kept showing the
  // first vendor's statement — the underlying purchase data was always
  // correct (verified directly in the DB), this tab just never re-synced
  // to the new `partner` query param once already mounted (same
  // `/accounting?tab=vendor-subledger` route both times, only the query
  // param changes, so the lazy useState initializers below only fire on
  // the very first mount). Comparing the incoming prop against what was
  // last synced, during render, is what actually re-triggers every time.
  const [syncedPartnerId, setSyncedPartnerId] = useState(initialPartnerId);
  if (initialPartnerId !== syncedPartnerId) {
    setPartnerId(initialPartnerId ?? "");
    setRanAt(initialPartnerId ? { partner: initialPartnerId, from: dateFrom, to: dateTo } : null);
    setSyncedPartnerId(initialPartnerId);
  }

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

// P0-2 (Phase-One period-closing GUI): the backend's FiscalPeriod
// mechanism (create + :close, FR-ACC-011) already exists and is already
// enforced centrally in JournalEntryService.post_entry for every module
// that posts a journal entry (Sales, Purchasing, Fixed Assets, Payments,
// manual JEs alike) — this tab is the missing surface for a user to
// actually reach it. Reuses the single existing
// accounting.fiscal_period.manage permission for both viewing and
// managing periods (no separate view-only tier exists in the backend).
// There is deliberately no "reopen" action: the backend has no reopen
// endpoint at all, so once closed a period stays closed.
function FiscalPeriodsTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [closing, setClosing] = useState<FiscalPeriod | null>(null);
  const [closeError, setCloseError] = useState<string | null>(null);

  const periodsQuery = useQuery({
    queryKey: ["fiscal-periods", companyId],
    queryFn: () => accountingApi.listFiscalPeriods(companyId),
  });
  const periods = periodsQuery.data ?? [];

  const createMutation = useMutation({
    mutationFn: () => accountingApi.createFiscalPeriod(companyId, { period_start: periodStart, period_end: periodEnd }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fiscal-periods", companyId] });
      toastSuccess(t("toast.success_title"), `${periodStart} — ${periodEnd}`);
      setPeriodStart("");
      setPeriodEnd("");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  const closeMutation = useMutation({
    mutationFn: () => accountingApi.closeFiscalPeriod(companyId, closing!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fiscal-periods", companyId] });
      toastSuccess(t("toast.success_title"), t("accounting.fiscal_periods.close_action"));
      setClosing(null);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setCloseError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  const columns: ERPColumn<FiscalPeriod>[] = [
    {
      key: "period_start",
      header: t("accounting.fiscal_periods.start_date"),
      sortable: true,
      sortValue: (r) => r.period_start,
      render: (r) => formatDate(r.period_start, locale),
    },
    {
      key: "period_end",
      header: t("accounting.fiscal_periods.end_date"),
      sortable: true,
      sortValue: (r) => r.period_end,
      render: (r) => formatDate(r.period_end, locale),
    },
    {
      key: "is_closed",
      header: t("accounting.fiscal_periods.status"),
      render: (r) => (
        <Badge variant={r.is_closed ? "outline" : "default"}>
          {r.is_closed ? t("accounting.fiscal_periods.closed") : t("accounting.fiscal_periods.open")}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (r) =>
        !r.is_closed && (
          <Can permission="accounting.fiscal_period.manage">
            <div className="flex justify-end">
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive"
                onClick={() => {
                  setClosing(r);
                  setCloseError(null);
                }}
              >
                {t("accounting.fiscal_periods.close_action")}
              </Button>
            </div>
          </Can>
        ),
    },
  ];

  return (
    <div className="space-y-4">
      <Can permission="accounting.fiscal_period.manage">
        <Card>
          <CardHeader>
            <CardTitle>{t("accounting.fiscal_periods.new")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.fiscal_periods.start_date")}</Label>
                <Input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} className="w-40" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.fiscal_periods.end_date")}</Label>
                <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} className="w-40" />
              </div>
              <Button
                size="sm"
                onClick={() => {
                  setError(null);
                  createMutation.mutate();
                }}
                disabled={!periodStart || !periodEnd || createMutation.isPending}
              >
                <Plus className="h-4 w-4" />
                {t("accounting.fiscal_periods.save")}
              </Button>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </Can>

      <ERPListView
        title={t("accounting.tabs.fiscal_periods")}
        columns={columns}
        rows={periods}
        rowKey={(r) => r.id}
        isLoading={periodsQuery.isLoading}
        isError={periodsQuery.isError}
        onRetry={() => periodsQuery.refetch()}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["fiscal-periods", companyId] })}
        emptyDescription={t("accounting.fiscal_periods.empty_description")}
      />

      <ConfirmDialog
        open={!!closing}
        onOpenChange={(open) => !open && setClosing(null)}
        title={t("accounting.fiscal_periods.close_confirm_title")}
        description={
          closeError
            ? closeError
            : `${closing ? `${formatDate(closing.period_start, locale)} – ${formatDate(closing.period_end, locale)}` : ""} ${t("accounting.fiscal_periods.close_confirm_body")}`
        }
        variant="destructive"
        confirmLabel={t("accounting.fiscal_periods.close_action")}
        onConfirm={() => closeMutation.mutate()}
        isPending={closeMutation.isPending}
      />
    </div>
  );
}

function CostCentersTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [nameAr, setNameAr] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<CostCenter | null>(null);
  const [editName, setEditName] = useState("");
  const [editNameAr, setEditNameAr] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  const costCentersQuery = useQuery({
    queryKey: ["cost-centers", companyId],
    queryFn: () => accountingApi.listCostCenters(companyId),
  });
  const costCenters = costCentersQuery.data ?? [];

  const createMutation = useMutation({
    mutationFn: () => accountingApi.createCostCenter(companyId, { name, name_ar: nameAr || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cost-centers", companyId] });
      toastSuccess(t("toast.success_title"), name);
      setName("");
      setNameAr("");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      accountingApi.updateCostCenter(companyId, editing!.id, { name: editName, name_ar: editNameAr || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cost-centers", companyId] });
      toastSuccess(t("toast.success_title"), editName);
      setEditing(null);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setEditError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: (cc: CostCenter) => accountingApi.updateCostCenter(companyId, cc.id, { is_active: !cc.is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cost-centers", companyId] });
      toastSuccess(t("toast.success_title"), t("accounting.cost_centers.tabs.title"));
    },
    onError: (err) => {
      toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error"));
    },
  });

  const columns: ERPColumn<CostCenter>[] = [
    { key: "name", header: t("accounting.cost_centers.name"), sortable: true, sortValue: (r) => r.name, render: (r) => r.name },
    { key: "name_ar", header: t("accounting.cost_centers.name_ar"), render: (r) => r.name_ar ?? "—" },
    {
      key: "is_active",
      header: t("accounting.cost_centers.status"),
      render: (r) => (
        <Badge variant={r.is_active ? "default" : "outline"}>
          {r.is_active ? t("accounting.cost_centers.active") : t("accounting.cost_centers.archived")}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (r) => (
        <Can permission="accounting.cost_centers.update">
          <div className="flex justify-end gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(r);
                setEditName(r.name);
                setEditNameAr(r.name_ar ?? "");
                setEditError(null);
              }}
            >
              {t("accounting.cost_centers.edit_action")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className={r.is_active ? "text-destructive" : undefined}
              onClick={() => toggleActiveMutation.mutate(r)}
              disabled={toggleActiveMutation.isPending}
            >
              {r.is_active ? t("accounting.cost_centers.archive_action") : t("accounting.cost_centers.reactivate_action")}
            </Button>
          </div>
        </Can>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <Can permission="accounting.cost_centers.create">
        <Card>
          <CardHeader>
            <CardTitle>{t("accounting.cost_centers.new")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.cost_centers.name")}</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("accounting.cost_centers.name_ar")}</Label>
                <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" className="w-48" />
              </div>
              <Button
                size="sm"
                onClick={() => {
                  setError(null);
                  createMutation.mutate();
                }}
                disabled={!name.trim() || createMutation.isPending}
              >
                <Plus className="h-4 w-4" />
                {t("accounting.cost_centers.save")}
              </Button>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </Can>

      <ERPListView
        title={t("accounting.cost_centers.tabs.title")}
        columns={columns}
        rows={costCenters}
        rowKey={(r) => r.id}
        isLoading={costCentersQuery.isLoading}
        isError={costCentersQuery.isError}
        onRetry={() => costCentersQuery.refetch()}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["cost-centers", companyId] })}
        emptyDescription={t("accounting.cost_centers.empty_description")}
      />

      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("accounting.cost_centers.edit_action")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">{t("accounting.cost_centers.name")}</Label>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("accounting.cost_centers.name_ar")}</Label>
              <Input value={editNameAr} onChange={(e) => setEditNameAr(e.target.value)} dir="rtl" />
            </div>
            {editError && <p className="text-sm text-destructive">{editError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => updateMutation.mutate()} disabled={!editName.trim() || updateMutation.isPending}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** The reason Cost Centers exist: for one cost center, every account it
 * actually touched in the period with a non-zero balance — revenue and
 * expense first, since that is the primary use case, but any account type
 * can appear (a cost center can carry any kind of line). */
function CostCenterReportTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [costCenterId, setCostCenterId] = useState("");
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ costCenter: string; from: string; to: string } | null>(null);

  const costCentersQuery = useQuery({
    queryKey: ["cost-centers", companyId],
    queryFn: () => accountingApi.listCostCenters(companyId),
  });
  const reportQuery = useQuery({
    queryKey: ["cost-center-report", companyId, ranAt?.costCenter, ranAt?.from, ranAt?.to],
    queryFn: () => accountingApi.costCenterReport(companyId, ranAt!.costCenter, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });
  const r = reportQuery.data;

  return (
    <ReportView
      title={t("accounting.ccr.title")}
      filterArea={
        <>
          <CostCenterFilterSelect
            value={costCenterId}
            onChange={setCostCenterId}
            costCenters={costCentersQuery.data ?? []}
          />
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
      onApply={
        costCenterId ? () => setRanAt({ costCenter: costCenterId, from: dateFrom, to: dateTo }) : undefined
      }
      onPrint={r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            `/api/v1/accounting/reports/cost-center/${ranAt.costCenter}`,
            { date_from: ranAt.from, date_to: ranAt.to, lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!r && r.accounts.length === 0}
      kpis={
        r
          ? [
              { label: t("accounting.is.total_revenue"), value: formatCurrency(r.revenue_total) },
              { label: t("accounting.ccr.total_expense"), value: formatCurrency(r.expense_total) },
              { label: t("accounting.ccr.net_result"), value: formatCurrency(r.net_result) },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("accounting.ccr.select_hint")}</p>}
      {r && (
        <>
          <ReportPrintHeader
            reportTitle={`${t("accounting.ccr.title")} — ${r.cost_center.name}`}
            dateRangeLabel={`${r.date_from} – ${r.date_to}`}
          />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("accounting.ccr.account_code")}</TableHead>
                <TableHead>{t("accounting.ccr.account")}</TableHead>
                <TableHead>{t("accounting.ccr.type")}</TableHead>
                <TableHead className="text-end">{t("accounting.ccr.balance")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {r.accounts.map((row) => (
                <TableRow key={row.account_id}>
                  <TableCell className="font-mono text-xs">{row.account_code}</TableCell>
                  <TableCell>
                    <Link
                      href={`/accounting?tab=general-ledger&account=${row.account_id}`}
                      className="underline-offset-4 hover:underline"
                    >
                      {row.account_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{t(`accounting.account_type.${row.type_code}`)}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(row.balance)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell colSpan={3}>{t("accounting.ccr.net_result")}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.net_result)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </>
      )}
    </ReportView>
  );
}

export default function AccountingPage() {
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
  // Owner-requested: the sidebar's "Accounting" group now lists every
  // report/screen directly (nav-config.ts), so picking one should land on
  // that screen alone — not also show a giant row of all 14 report names
  // as tab buttons (which wrapped across several lines and was itself
  // what pushed each report's own "Apply" filter button below the fold).
  return (
    <div className="space-y-6">
      {tab === "accounts" && <ChartOfAccountsTab />}
      {tab === "journal-entries" && <JournalEntriesTab />}
      {tab === "trial-balance" && <TrialBalanceTab />}
      {tab === "general-ledger" && <GeneralLedgerTab initialAccountId={deepLinkAccountId} />}
      {tab === "income-statement" && <IncomeStatementTab />}
      {tab === "balance-sheet" && <BalanceSheetTab />}
      {tab === "cash-flow" && <CashFlowTab />}
      {tab === "vat-summary" && <VatSummaryTab />}
      {tab === "customer-subledger" && <CustomerSubledgerTab initialPartnerId={deepLinkPartnerId} />}
      {tab === "vendor-subledger" && <VendorSubledgerTab initialPartnerId={deepLinkPartnerId} />}
      {tab === "ar-aging" && <ArAgingTab />}
      {tab === "ap-aging" && <ApAgingTab />}
      {tab === "fiscal-periods" && <FiscalPeriodsTab />}
      {tab === "cost-centers" && <CostCentersTab />}
      {tab === "cost-center-report" && <CostCenterReportTab />}
    </div>
  );
}
