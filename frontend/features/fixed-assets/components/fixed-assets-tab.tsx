"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { CategorySelect } from "@/components/erp/category-select/category-select";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import { fixedAssetsApi } from "@/features/fixed-assets/api/client";
import type { AssetOperationalStatus, FixedAsset, RunDepreciationResult } from "@/features/fixed-assets/api/types";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { toastError, toastSuccess } from "@/lib/toast";
import { downloadReportExport } from "@/lib/report-export";
import { ApiError } from "@/lib/api-client";

export function FixedAssetsTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [nameAr, setNameAr] = useState("");
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [fixedAssetAccountId, setFixedAssetAccountId] = useState("");
  const [accumAccountId, setAccumAccountId] = useState("");
  const [expenseAccountId, setExpenseAccountId] = useState("");
  const [fundingAccountId, setFundingAccountId] = useState("");
  const [acquisitionDate, setAcquisitionDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [cost, setCost] = useState("");
  const [salvageValue, setSalvageValue] = useState("0");
  const [usefulLifeMonths, setUsefulLifeMonths] = useState("60");
  const [assetStatus, setAssetStatus] = useState<AssetOperationalStatus>("active");
  const [createError, setCreateError] = useState<string | null>(null);

  const [filterStatus, setFilterStatus] = useState<"" | AssetOperationalStatus | "disposed">("");
  const [filterCategoryId, setFilterCategoryId] = useState<string | null>(null);

  const [runOpen, setRunOpen] = useState(false);
  const [periodMonth, setPeriodMonth] = useState(() => new Date().toISOString().slice(0, 10));
  const [runScope, setRunScope] = useState<"all" | "category">("all");
  const [runCategoryId, setRunCategoryId] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<RunDepreciationResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const [disposing, setDisposing] = useState<FixedAsset | null>(null);
  const [disposalDate, setDisposalDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [proceeds, setProceeds] = useState("0");
  const [proceedsAccountId, setProceedsAccountId] = useState("");
  const [gainLossAccountId, setGainLossAccountId] = useState("");
  const [disposeError, setDisposeError] = useState<string | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["accounts", companyId],
    queryFn: () => accountingApi.listAccounts(companyId),
  });
  // Same guard the Journal Entry line picker already applies: a group
  // account can never be posted to, so it's excluded here too rather than
  // relying only on the 422 the backend would otherwise return.
  const postingAccounts = (accountsQuery.data ?? []).filter((a) => !a.is_group);

  const categoriesQuery = useQuery({
    queryKey: ["fixed-asset-categories", companyId],
    queryFn: () => fixedAssetsApi.listCategories(companyId),
  });

  const assetsQuery = useQuery({
    queryKey: ["fixed-assets", companyId, filterStatus, filterCategoryId],
    queryFn: () =>
      fixedAssetsApi.listAssets(companyId, {
        status: filterStatus || undefined,
        categoryId: filterCategoryId || undefined,
      }),
  });
  // Sum of ACTIVE assets only -- a disposed asset's cost/accumulated
  // depreciation were already cleared out of the GL by its disposal entry,
  // so including it here would make this total permanently disagree with
  // the Trial Balance (see the /fixed-assets/reconciliation endpoint,
  // which applies the same active-only rule for the same reason).
  const registerTotals = assetsQuery.data
    ? assetsQuery.data
        .filter((a) => a.status !== "disposed")
        .reduce(
          (acc, a) => ({
            cost: acc.cost + Number(a.cost),
            accumulated_depreciation: acc.accumulated_depreciation + Number(a.accumulated_depreciation),
            net_book_value: acc.net_book_value + Number(a.net_book_value),
          }),
          { cost: 0, accumulated_depreciation: 0, net_book_value: 0 }
        )
    : null;

  const createMutation = useMutation({
    mutationFn: () =>
      fixedAssetsApi.createAsset(companyId, branchId, {
        name,
        name_ar: nameAr || null,
        category_id: categoryId,
        fixed_asset_account_id: fixedAssetAccountId,
        accumulated_depreciation_account_id: accumAccountId,
        depreciation_expense_account_id: expenseAccountId,
        funding_account_id: fundingAccountId,
        acquisition_date: acquisitionDate,
        cost,
        salvage_value: salvageValue,
        useful_life_months: Number(usefulLifeMonths),
        status: assetStatus,
      }),
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: ["fixed-assets", companyId] });
      toastSuccess(t("toast.success_title"), asset.asset_code);
      setName("");
      setNameAr("");
      setCategoryId(null);
      setFixedAssetAccountId("");
      setAccumAccountId("");
      setExpenseAccountId("");
      setFundingAccountId("");
      setCost("");
      setSalvageValue("0");
      setUsefulLifeMonths("60");
      setAssetStatus("active");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setCreateError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  const runMutation = useMutation({
    mutationFn: () =>
      fixedAssetsApi.runDepreciation(
        companyId,
        branchId,
        periodMonth,
        runScope === "category" ? runCategoryId : null
      ),
    onSuccess: (result) => {
      setRunResult(result);
      setRunError(null);
      queryClient.invalidateQueries({ queryKey: ["fixed-assets", companyId] });
      toastSuccess(t("toast.success_title"), `${result.assets_posted} — ${formatCurrency(result.total_amount)}`);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setRunError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  const disposeMutation = useMutation({
    mutationFn: () =>
      fixedAssetsApi.disposeAsset(companyId, branchId, disposing!.id, {
        disposal_date: disposalDate,
        proceeds,
        proceeds_account_id: proceedsAccountId || null,
        gain_loss_account_id: gainLossAccountId || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fixed-assets", companyId] });
      toastSuccess(t("toast.success_title"), t("fixed_assets.dispose.title"));
      setDisposing(null);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setDisposeError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  // Owner decision (2026-08-19): a category may carry a default policy
  // (useful life + the three GL accounts) that prefills a NEW asset's form
  // when picked -- every field stays fully editable afterward, this is a
  // convenience prefill only, never enforced.
  function handleCategoryChange(newCategoryId: string | null) {
    setCategoryId(newCategoryId);
    const category = categoriesQuery.data?.find((c) => c.id === newCategoryId);
    if (!category) return;
    if (category.default_useful_life_months != null) {
      setUsefulLifeMonths(String(category.default_useful_life_months));
    }
    if (category.default_fixed_asset_account_id) setFixedAssetAccountId(category.default_fixed_asset_account_id);
    if (category.default_accumulated_depreciation_account_id) {
      setAccumAccountId(category.default_accumulated_depreciation_account_id);
    }
    if (category.default_depreciation_expense_account_id) {
      setExpenseAccountId(category.default_depreciation_expense_account_id);
    }
  }

  const usefulLifeMonthsNum = Number(usefulLifeMonths);
  const derivedRatePercent =
    usefulLifeMonthsNum > 0 ? (1200 / usefulLifeMonthsNum).toFixed(2) : null;

  function openDispose(asset: FixedAsset) {
    setDisposing(asset);
    setDisposalDate(new Date().toISOString().slice(0, 10));
    setProceeds("0");
    setProceedsAccountId("");
    setGainLossAccountId("");
    setDisposeError(null);
  }

  const columns: ERPColumn<FixedAsset>[] = [
    {
      key: "asset_code",
      header: t("fixed_assets.code"),
      sortable: true,
      sortValue: (r) => r.asset_code,
      render: (r) => (
        <Link
          href={`/fixed-assets/card?asset=${r.id}`}
          className="font-mono underline-offset-4 hover:underline"
          title={t("fixed_assets.card.drill_down_hint")}
        >
          {r.asset_code}
        </Link>
      ),
    },
    { key: "name", header: t("fixed_assets.name"), sortable: true, sortValue: (r) => r.name, render: (r) => r.name },
    {
      key: "category",
      header: t("fixed_assets.category"),
      sortable: true,
      sortValue: (r) => categoriesQuery.data?.find((c) => c.id === r.category_id)?.name ?? "",
      render: (r) => categoriesQuery.data?.find((c) => c.id === r.category_id)?.name ?? "—",
    },
    {
      key: "acquisition_date",
      header: t("fixed_assets.acquisition_date"),
      sortable: true,
      sortValue: (r) => r.acquisition_date,
      render: (r) => formatDate(r.acquisition_date, locale),
    },
    {
      key: "cost",
      header: t("fixed_assets.cost"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.cost),
      render: (r) => formatCurrency(r.cost),
    },
    {
      key: "accumulated_depreciation",
      header: t("fixed_assets.accumulated_depreciation"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.accumulated_depreciation),
      render: (r) => formatCurrency(r.accumulated_depreciation),
    },
    {
      key: "net_book_value",
      header: t("fixed_assets.net_book_value"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.net_book_value),
      render: (r) => formatCurrency(r.net_book_value),
    },
    {
      key: "status",
      header: t("fixed_assets.status"),
      sortable: true,
      sortValue: (r) =>
        r.status === "disposed"
          ? t("fixed_assets.status_disposed")
          : r.fully_depreciated
            ? t("fixed_assets.status_fully_depreciated")
            : t(`fixed_assets.status_${r.status}`),
      render: (r) => (
        <Badge
          variant={
            r.status === "disposed"
              ? "secondary"
              : r.fully_depreciated
                ? "warning"
                : r.status === "active"
                  ? "default"
                  : "outline"
          }
        >
          {r.status === "disposed"
            ? t("fixed_assets.status_disposed")
            : r.fully_depreciated
              ? t("fixed_assets.status_fully_depreciated")
              : t(`fixed_assets.status_${r.status}`)}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (r) =>
        r.status !== "disposed" ? (
          <Can permission="fixed_assets.dispose">
            <div className="flex justify-end">
              <Button size="sm" variant="ghost" onClick={() => openDispose(r)}>
                {t("fixed_assets.dispose.action")}
              </Button>
            </div>
          </Can>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      <Can permission="fixed_assets.create">
        <Card>
          <CardHeader>
            <CardTitle>{t("fixed_assets.new")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="space-y-1">
                <Label className="text-xs">{t("fixed_assets.name")}</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("fixed_assets.name_ar")}</Label>
                <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("fixed_assets.category")}</Label>
                <CategorySelect
                  categories={categoriesQuery.data ?? []}
                  value={categoryId}
                  onChange={handleCategoryChange}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("fixed_assets.status")}</Label>
                <Select value={assetStatus} onValueChange={(v) => setAssetStatus(v as AssetOperationalStatus)}>
                  <SelectTrigger className="w-full">
                    <SelectValue>{(v: string) => t(`fixed_assets.status_${v}`)}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">{t("fixed_assets.status_active")}</SelectItem>
                    <SelectItem value="idle">{t("fixed_assets.status_idle")}</SelectItem>
                    <SelectItem value="under_maintenance">{t("fixed_assets.status_under_maintenance")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("fixed_assets.acquisition_date")}</Label>
                <Input type="date" value={acquisitionDate} onChange={(e) => setAcquisitionDate(e.target.value)} />
                <p className="text-xs text-muted-foreground">{t("fixed_assets.acquisition_date.full_month_hint")}</p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("fixed_assets.cost")}</Label>
                <Input type="number" min="0" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("fixed_assets.salvage_value")}</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={salvageValue}
                  onChange={(e) => setSalvageValue(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("fixed_assets.useful_life_months")}</Label>
                <Input
                  type="number"
                  min="1"
                  step="1"
                  value={usefulLifeMonths}
                  onChange={(e) => setUsefulLifeMonths(e.target.value)}
                />
                {derivedRatePercent && (
                  <p className="text-xs text-muted-foreground">
                    {t("fixed_assets.depreciation_rate_percent")}: {derivedRatePercent}%
                  </p>
                )}
              </div>
              <AccountSelect
                label={t("fixed_assets.fixed_asset_account")}
                value={fixedAssetAccountId}
                onChange={setFixedAssetAccountId}
                options={postingAccounts}
              />
              <AccountSelect
                label={t("fixed_assets.accumulated_depreciation_account")}
                value={accumAccountId}
                onChange={setAccumAccountId}
                options={postingAccounts}
              />
              <AccountSelect
                label={t("fixed_assets.depreciation_expense_account")}
                value={expenseAccountId}
                onChange={setExpenseAccountId}
                options={postingAccounts}
              />
              <AccountSelect
                label={t("fixed_assets.funding_account")}
                value={fundingAccountId}
                onChange={setFundingAccountId}
                options={postingAccounts}
              />
            </div>
            <Button
              size="sm"
              onClick={() => {
                setCreateError(null);
                createMutation.mutate();
              }}
              disabled={
                !name ||
                !cost ||
                !fixedAssetAccountId ||
                !accumAccountId ||
                !expenseAccountId ||
                !fundingAccountId ||
                createMutation.isPending
              }
            >
              <Plus className="h-4 w-4" />
              {t("fixed_assets.save")}
            </Button>
            {createError && <p className="text-sm text-destructive">{createError}</p>}
          </CardContent>
        </Card>
      </Can>

      <Can permission="fixed_assets.depreciation.run">
        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setRunResult(null);
              setRunError(null);
              setRunOpen(true);
            }}
          >
            {t("fixed_assets.run.action")}
          </Button>
        </div>
      </Can>

      {registerTotals && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-muted-foreground">{t("fixed_assets.totals.cost")}</p>
              <p className="font-mono text-lg font-semibold">{formatCurrency(registerTotals.cost)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-muted-foreground">{t("fixed_assets.totals.accumulated_depreciation")}</p>
              <p className="font-mono text-lg font-semibold">
                {formatCurrency(registerTotals.accumulated_depreciation)}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-muted-foreground">{t("fixed_assets.totals.net_book_value")}</p>
              <p className="font-mono text-lg font-semibold">{formatCurrency(registerTotals.net_book_value)}</p>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-48 space-y-1">
            <Label className="text-xs">{t("fixed_assets.filter.status")}</Label>
            <Select
              value={filterStatus || "__all__"}
              onValueChange={(v) =>
                setFilterStatus(v === "__all__" ? "" : (v as AssetOperationalStatus | "disposed"))
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue>
                  {(v: string) => (v === "__all__" ? t("fixed_assets.filter.status_all") : t(`fixed_assets.status_${v}`))}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">{t("fixed_assets.filter.status_all")}</SelectItem>
                <SelectItem value="active">{t("fixed_assets.status_active")}</SelectItem>
                <SelectItem value="idle">{t("fixed_assets.status_idle")}</SelectItem>
                <SelectItem value="under_maintenance">{t("fixed_assets.status_under_maintenance")}</SelectItem>
                <SelectItem value="disposed">{t("fixed_assets.status_disposed")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="w-56 space-y-1">
            <Label className="text-xs">{t("fixed_assets.filter.category")}</Label>
            <CategorySelect
              categories={categoriesQuery.data ?? []}
              value={filterCategoryId}
              onChange={setFilterCategoryId}
              placeholder={t("fixed_assets.filter.all_categories")}
            />
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              downloadReportExport(
                "/api/v1/fixed-assets",
                { status_filter: filterStatus || undefined, category_id: filterCategoryId || undefined, lang: locale },
                "pdf",
                companyId
              ).catch((e) => toastError(e instanceof Error ? e.message : String(e)))
            }
          >
            <Download className="h-4 w-4" />
            PDF
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              downloadReportExport(
                "/api/v1/fixed-assets",
                { status_filter: filterStatus || undefined, category_id: filterCategoryId || undefined, lang: locale },
                "xlsx",
                companyId
              ).catch((e) => toastError(e instanceof Error ? e.message : String(e)))
            }
          >
            <Download className="h-4 w-4" />
            Excel
          </Button>
        </div>
      </div>

      <ERPListView
        title={t("accounting.tabs.fixed_assets")}
        columns={columns}
        rows={assetsQuery.data ?? []}
        rowKey={(r) => r.id}
        isLoading={assetsQuery.isLoading}
        isError={assetsQuery.isError}
        onRetry={() => assetsQuery.refetch()}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["fixed-assets", companyId] })}
        searchText={(r) => `${r.asset_code} ${r.name} ${r.name_ar ?? ""}`}
        searchPlaceholder={t("list.search_placeholder")}
        emptyDescription={t("common.empty")}
      />

      <Dialog open={runOpen} onOpenChange={setRunOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("fixed_assets.run.title")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">{t("fixed_assets.run.period_month")}</Label>
              <Input type="date" value={periodMonth} onChange={(e) => setPeriodMonth(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("fixed_assets.run.scope")}</Label>
              <Select
                value={runScope}
                onValueChange={(v) => {
                  setRunScope((v as "all" | "category") ?? "all");
                  if (v !== "category") setRunCategoryId(null);
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>
                    {(v: string) => (v === "category" ? t("fixed_assets.run.scope_category") : t("fixed_assets.run.scope_all"))}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("fixed_assets.run.scope_all")}</SelectItem>
                  <SelectItem value="category">{t("fixed_assets.run.scope_category")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {runScope === "category" && (
              <div className="space-y-1">
                <Label className="text-xs">{t("fixed_assets.filter.category")}</Label>
                <CategorySelect
                  categories={categoriesQuery.data ?? []}
                  value={runCategoryId}
                  onChange={setRunCategoryId}
                />
              </div>
            )}
            {runError && <p className="text-sm text-destructive">{runError}</p>}
            {runResult && (
              <div className="rounded-md border p-3 text-sm space-y-1">
                <p>
                  {t("fixed_assets.run.posted")}: {runResult.assets_posted} ({formatCurrency(runResult.total_amount)})
                </p>
                <p>
                  {t("fixed_assets.run.skipped")}: {runResult.assets_skipped}
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRunOpen(false)}>
              {t("common.close")}
            </Button>
            <Button
              disabled={runMutation.isPending || (runScope === "category" && !runCategoryId)}
              onClick={() => runMutation.mutate()}
            >
              {runMutation.isPending ? t("common.loading") : t("fixed_assets.run.action")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!disposing} onOpenChange={(open) => !open && setDisposing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("fixed_assets.dispose.title")} — {disposing?.asset_code}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {t("fixed_assets.net_book_value")}: {disposing && formatCurrency(disposing.net_book_value)}
            </p>
            <div className="space-y-1">
              <Label className="text-xs">{t("fixed_assets.dispose.disposal_date")}</Label>
              <Input type="date" value={disposalDate} onChange={(e) => setDisposalDate(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t("fixed_assets.dispose.proceeds")}</Label>
              <Input type="number" min="0" step="0.01" value={proceeds} onChange={(e) => setProceeds(e.target.value)} />
            </div>
            <AccountSelect
              label={t("fixed_assets.dispose.proceeds_account")}
              value={proceedsAccountId}
              onChange={setProceedsAccountId}
              options={postingAccounts}
              optional
            />
            <AccountSelect
              label={t("fixed_assets.dispose.gain_loss_account")}
              value={gainLossAccountId}
              onChange={setGainLossAccountId}
              options={postingAccounts}
              optional
            />
            {disposeError && <p className="text-sm text-destructive">{disposeError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisposing(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={disposeMutation.isPending}
              onClick={() => {
                setDisposeError(null);
                disposeMutation.mutate();
              }}
            >
              {disposeMutation.isPending ? t("common.loading") : t("fixed_assets.dispose.action")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AccountSelect({
  label,
  value,
  onChange,
  options,
  optional = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { id: string; code: string; name: string }[];
  optional?: boolean;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">
        {label}
        {optional ? "" : " *"}
      </Label>
      <Select value={value} onValueChange={(v) => onChange(v ?? "")}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="—">
            {(v: string) => {
              const acc = options.find((a) => a.id === v);
              return acc ? `${acc.code} — ${acc.name}` : v;
            }}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {options.map((a) => (
            <SelectItem key={a.id} value={a.id}>
              {a.code} — {a.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
