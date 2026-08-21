"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableFooter, TableHeader, TableRow } from "@/components/ui/table";
import { EntitySearchSelect } from "@/components/erp/entity-search-select/entity-search-select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { SortableTableHead } from "@/components/erp/report-view/sortable-table-head";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { fixedAssetsApi } from "@/features/fixed-assets/api/client";
import type { AssetOperationalStatus } from "@/features/fixed-assets/api/types";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { reportExportHandlers } from "@/lib/report-export";
import { toastError, toastSuccess } from "@/lib/toast";
import { useSortedRows } from "@/lib/use-sorted-rows";
import { ApiError } from "@/lib/api-client";

/** بطاقة الأصل الثابت — same opening/running/closing shape as the
 * Customer/Vendor Subledger and Product Cardex, but tracking three
 * parallel running values (cost, accumulated depreciation, net book
 * value) since a fixed asset's movements come from two sources: the
 * asset row itself (acquisition/disposal) and its depreciation entries. */
export function FixedAssetCardTab({ initialAssetId }: { initialAssetId?: string }) {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const [dateFrom, setDateFrom] = useState(() => `${new Date().getFullYear()}-01-01`);
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [assetId, setAssetId] = useState(initialAssetId ?? "");
  const [ranAt, setRanAt] = useState<{ asset: string; from: string; to: string } | null>(() =>
    initialAssetId ? { asset: initialAssetId, from: dateFrom, to: dateTo } : null
  );
  // Same class of bug found and fixed in accounting/page.tsx's
  // Customer/Vendor Subledger and General Ledger tabs: drilling into a
  // different asset while this tab is already mounted (same route, only
  // the `asset` query param changes) would silently keep showing the
  // first asset's card, since the lazy useState initializers above only
  // fire on the very first mount.
  const [syncedAssetId, setSyncedAssetId] = useState(initialAssetId);
  if (initialAssetId !== syncedAssetId) {
    setAssetId(initialAssetId ?? "");
    setRanAt(initialAssetId ? { asset: initialAssetId, from: dateFrom, to: dateTo } : null);
    setSyncedAssetId(initialAssetId);
  }

  const assetsQuery = useQuery({
    queryKey: ["fixed-assets", companyId],
    queryFn: () => fixedAssetsApi.listAssets(companyId),
  });
  const cardQuery = useQuery({
    queryKey: ["fixed-asset-card", companyId, ranAt?.asset, ranAt?.from, ranAt?.to],
    queryFn: () => fixedAssetsApi.getAssetCard(companyId, ranAt!.asset, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });
  const r = cardQuery.data;

  // Asset Master + Depreciation Policy (Owner brief §13: opening an asset
  // must show why it's at its current value) -- the card above answers
  // the movement/accounting-entries half; this answers the policy half.
  const assetQuery = useQuery({
    queryKey: ["fixed-asset", companyId, ranAt?.asset],
    queryFn: () => fixedAssetsApi.getAsset(companyId, ranAt!.asset),
    enabled: !!ranAt,
  });
  const scheduleQuery = useQuery({
    queryKey: ["fixed-asset-projected-schedule", companyId, ranAt?.asset],
    queryFn: () => fixedAssetsApi.getProjectedSchedule(companyId, ranAt!.asset),
    enabled: !!ranAt,
  });
  const { sort: movementSort, toggleSort: toggleMovementSort, sortedRows: sortedMovementLines } = useSortedRows(
    r?.lines,
    {
      date: (l) => l.date,
      movement_type: (l) => t(`fixed_assets.card.movement.${l.movement_type}`),
      reference: (l) => l.reference,
      running_cost: (l) => Number(l.running_cost),
      running_accumulated_depreciation: (l) => Number(l.running_accumulated_depreciation),
      running_net_book_value: (l) => Number(l.running_net_book_value),
    }
  );
  const movementLines = sortedMovementLines ?? r?.lines ?? [];
  const { sort: scheduleSort, toggleSort: toggleScheduleSort, sortedRows: sortedScheduleLines } = useSortedRows(
    scheduleQuery.data?.lines,
    {
      period_month: (l) => l.period_month,
      depreciation: (l) => Number(l.depreciation),
      accumulated_depreciation: (l) => Number(l.accumulated_depreciation),
      net_book_value: (l) => Number(l.net_book_value),
      posted: (l) => (l.posted ? 1 : 0),
    }
  );
  const scheduleLines = sortedScheduleLines ?? scheduleQuery.data?.lines ?? [];

  const statusMutation = useMutation({
    mutationFn: (newStatus: AssetOperationalStatus) =>
      fixedAssetsApi.updateAssetStatus(companyId, ranAt!.asset, newStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fixed-asset", companyId, ranAt?.asset] });
      queryClient.invalidateQueries({ queryKey: ["fixed-assets", companyId] });
      toastSuccess(t("toast.success_title"), t("fixed_assets.status"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  return (
    <ReportView
      title={t("fixed_assets.card.title")}
      filterArea={
        <>
          <div className="w-64 space-y-1">
            <Label className="text-xs">{t("fixed_assets.card.select_asset")}</Label>
            <EntitySearchSelect
              items={(assetsQuery.data ?? []).map((a) => ({ id: a.id, label: a.name, code: a.asset_code }))}
              value={assetId || null}
              onChange={(v) => setAssetId(v ?? "")}
              placeholder={t("fixed_assets.card.select_asset")}
            />
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
      onApply={assetId ? () => setRanAt({ asset: assetId, from: dateFrom, to: dateTo }) : undefined}
      onPrint={ranAt && r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            `/api/v1/fixed-assets/${ranAt.asset}/card`,
            { date_from: ranAt.from, date_to: ranAt.to, lang: locale },
            companyId
          )
        : {})}
      isLoading={cardQuery.isLoading}
      isError={cardQuery.isError}
      onRetry={() => cardQuery.refetch()}
      kpis={
        r
          ? [
              { label: t("fixed_assets.cost"), value: formatCurrency(r.closing_cost) },
              { label: t("fixed_assets.accumulated_depreciation"), value: formatCurrency(r.closing_accumulated_depreciation) },
              { label: t("fixed_assets.net_book_value"), value: formatCurrency(r.closing_net_book_value) },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("fixed_assets.card.select_asset_hint")}</p>}
      {ranAt && r && (
        <>
          <ReportPrintHeader
            reportTitle={t("fixed_assets.card.title")}
            subtitle={`${r.asset_code} — ${r.asset_name}`}
            dateRangeLabel={`${r.date_from} – ${r.date_to}`}
          />
          {assetQuery.data && (
            <div className="mb-4 grid grid-cols-2 gap-x-6 gap-y-2 rounded-md border p-3 text-sm sm:grid-cols-4">
              <div>
                <p className="text-xs text-muted-foreground">{t("fixed_assets.cost")}</p>
                <p className="font-mono">{formatCurrency(assetQuery.data.cost)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t("fixed_assets.salvage_value")}</p>
                <p className="font-mono">{formatCurrency(assetQuery.data.salvage_value)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t("fixed_assets.useful_life_months")}</p>
                <p className="font-mono">{assetQuery.data.useful_life_months}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t("fixed_assets.depreciation_rate_percent")}</p>
                <p className="font-mono">{assetQuery.data.depreciation_rate_percent}%</p>
              </div>
              <div className="col-span-2 flex items-center gap-2 sm:col-span-4">
                <p className="text-xs text-muted-foreground">{t("fixed_assets.status")}:</p>
                {assetQuery.data.status === "disposed" ? (
                  <Badge variant="secondary">{t("fixed_assets.status_disposed")}</Badge>
                ) : (
                  <Select
                    value={assetQuery.data.status}
                    onValueChange={(v) => statusMutation.mutate(v as AssetOperationalStatus)}
                  >
                    <SelectTrigger className="w-48">
                      <SelectValue>{(v: string) => t(`fixed_assets.status_${v}`)}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">{t("fixed_assets.status_active")}</SelectItem>
                      <SelectItem value="idle">{t("fixed_assets.status_idle")}</SelectItem>
                      <SelectItem value="under_maintenance">{t("fixed_assets.status_under_maintenance")}</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <SortableTableHead sortKey="date" sort={movementSort} onSort={toggleMovementSort}>
                  {t("accounting.sub.date")}
                </SortableTableHead>
                <SortableTableHead sortKey="movement_type" sort={movementSort} onSort={toggleMovementSort}>
                  {t("fixed_assets.card.movement_type")}
                </SortableTableHead>
                <SortableTableHead sortKey="reference" sort={movementSort} onSort={toggleMovementSort}>
                  {t("accounting.sub.reference")}
                </SortableTableHead>
                <SortableTableHead sortKey="running_cost" sort={movementSort} onSort={toggleMovementSort} align="end">
                  {t("fixed_assets.cost")}
                </SortableTableHead>
                <SortableTableHead
                  sortKey="running_accumulated_depreciation"
                  sort={movementSort}
                  onSort={toggleMovementSort}
                  align="end"
                >
                  {t("fixed_assets.accumulated_depreciation")}
                </SortableTableHead>
                <SortableTableHead
                  sortKey="running_net_book_value"
                  sort={movementSort}
                  onSort={toggleMovementSort}
                  align="end"
                >
                  {t("fixed_assets.net_book_value")}
                </SortableTableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow className="italic text-muted-foreground">
                <TableCell colSpan={3}>{t("accounting.sub.opening_balance")}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.opening_cost)}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.opening_accumulated_depreciation)}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.opening_net_book_value)}</TableCell>
              </TableRow>
              {movementLines.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    {t("common.empty")}
                  </TableCell>
                </TableRow>
              )}
              {movementLines.map((line, i) => (
                <TableRow key={i}>
                  <TableCell>{formatDate(line.date, locale)}</TableCell>
                  <TableCell>{t(`fixed_assets.card.movement.${line.movement_type}`)}</TableCell>
                  <TableCell>{line.reference}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(line.running_cost)}</TableCell>
                  <TableCell className="text-end font-mono">
                    {formatCurrency(line.running_accumulated_depreciation)}
                  </TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(line.running_net_book_value)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow className="font-semibold">
                <TableCell colSpan={3}>{t("accounting.sub.closing_balance")}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.closing_cost)}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.closing_accumulated_depreciation)}</TableCell>
                <TableCell className="text-end font-mono">{formatCurrency(r.closing_net_book_value)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>

          {scheduleQuery.data && (
            <div className="mt-6 print:hidden">
              <h3 className="mb-2 text-sm font-semibold">{t("fixed_assets.card.schedule.title")}</h3>
              <p className="mb-2 text-xs text-muted-foreground">{t("fixed_assets.card.schedule.hint")}</p>
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableTableHead sortKey="period_month" sort={scheduleSort} onSort={toggleScheduleSort}>
                      {t("fixed_assets.card.schedule.period")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="depreciation" sort={scheduleSort} onSort={toggleScheduleSort} align="end">
                      {t("fixed_assets.card.schedule.depreciation")}
                    </SortableTableHead>
                    <SortableTableHead
                      sortKey="accumulated_depreciation"
                      sort={scheduleSort}
                      onSort={toggleScheduleSort}
                      align="end"
                    >
                      {t("fixed_assets.accumulated_depreciation")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="net_book_value" sort={scheduleSort} onSort={toggleScheduleSort} align="end">
                      {t("fixed_assets.net_book_value")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="posted" sort={scheduleSort} onSort={toggleScheduleSort}>
                      {t("fixed_assets.card.schedule.status")}
                    </SortableTableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {scheduleLines.map((line) => (
                    <TableRow key={line.period_month} className={line.posted ? undefined : "text-muted-foreground"}>
                      <TableCell>{line.period_month.slice(0, 7)}</TableCell>
                      <TableCell className="text-end font-mono">{formatCurrency(line.depreciation)}</TableCell>
                      <TableCell className="text-end font-mono">
                        {formatCurrency(line.accumulated_depreciation)}
                      </TableCell>
                      <TableCell className="text-end font-mono">{formatCurrency(line.net_book_value)}</TableCell>
                      <TableCell>
                        {line.posted ? (
                          <Badge variant="default">{t("fixed_assets.card.schedule.posted")}</Badge>
                        ) : (
                          <Badge variant="outline">{t("fixed_assets.card.schedule.projected")}</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
    </ReportView>
  );
}
