"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableFooter, TableHeader, TableRow } from "@/components/ui/table";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { CategorySelect } from "@/components/erp/category-select/category-select";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { SortableTableHead } from "@/components/erp/report-view/sortable-table-head";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { fixedAssetsApi } from "@/features/fixed-assets/api/client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { reportExportHandlers } from "@/lib/report-export";
import { useSortedRows } from "@/lib/use-sorted-rows";

/** Company-wide standard report: every depreciation entry actually posted
 * within a period range — the "rest of the standard reports" the Owner
 * asked for, alongside the Register (list export) and the already-shipped
 * GL Reconciliation. */
export function FixedAssetsDepreciationScheduleTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [dateFrom, setDateFrom] = useState(() => `${new Date().getFullYear()}-01-01`);
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [ranAt, setRanAt] = useState<{ from: string; to: string; category: string | null } | null>(null);

  const categoriesQuery = useQuery({
    queryKey: ["fixed-asset-categories", companyId],
    queryFn: () => fixedAssetsApi.listCategories(companyId),
  });

  const reportQuery = useQuery({
    queryKey: ["fixed-assets-depreciation-schedule", companyId, ranAt?.from, ranAt?.to, ranAt?.category],
    queryFn: () =>
      fixedAssetsApi.getDepreciationSchedule(companyId, ranAt!.from, ranAt!.to, ranAt?.category ?? undefined),
    enabled: !!ranAt,
  });
  const r = reportQuery.data;
  const { sort, toggleSort, sortedRows } = useSortedRows(r?.lines, {
    period_month: (l) => l.period_month,
    asset_code: (l) => l.asset_code,
    asset_name: (l) => l.asset_name,
    amount: (l) => Number(l.amount),
  });
  const lines = sortedRows ?? r?.lines ?? [];

  return (
    <ReportView
      title={t("fixed_assets.schedule.title")}
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
          <div className="w-56 space-y-1">
            <Label className="text-xs">{t("fixed_assets.filter.category")}</Label>
            <CategorySelect
              categories={categoriesQuery.data ?? []}
              value={categoryId}
              onChange={setCategoryId}
              placeholder={t("fixed_assets.filter.all_categories")}
            />
          </div>
        </>
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo, category: categoryId })}
      onPrint={r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/fixed-assets/depreciation-schedule",
            { date_from: ranAt.from, date_to: ranAt.to, category_id: ranAt.category ?? undefined, lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      kpis={r ? [{ label: t("fixed_assets.schedule.total_depreciation"), value: formatCurrency(r.total_amount) }] : undefined}
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("fixed_assets.schedule.hint")}</p>}
      {ranAt && r && (
        <>
          <ReportPrintHeader reportTitle={t("fixed_assets.schedule.title")} dateRangeLabel={`${r.date_from} – ${r.date_to}`} />
          <Table>
            <TableHeader>
              <TableRow>
                <SortableTableHead sortKey="period_month" sort={sort} onSort={toggleSort}>
                  {t("fixed_assets.schedule.period")}
                </SortableTableHead>
                <SortableTableHead sortKey="asset_code" sort={sort} onSort={toggleSort}>
                  {t("fixed_assets.code")}
                </SortableTableHead>
                <SortableTableHead sortKey="asset_name" sort={sort} onSort={toggleSort}>
                  {t("fixed_assets.name")}
                </SortableTableHead>
                <SortableTableHead sortKey="amount" sort={sort} onSort={toggleSort} align="end">
                  {t("payments.amount")}
                </SortableTableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    {t("common.empty")}
                  </TableCell>
                </TableRow>
              )}
              {lines.map((line, i) => (
                <TableRow key={i}>
                  <TableCell>{formatDate(line.period_month, locale)}</TableCell>
                  <TableCell className="font-mono">{line.asset_code}</TableCell>
                  <TableCell>{line.asset_name}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(line.amount)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            {r.lines.length > 0 && (
              <TableFooter>
                <TableRow className="font-semibold">
                  <TableCell colSpan={3}>{t("fixed_assets.schedule.total_depreciation")}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(r.total_amount)}</TableCell>
                </TableRow>
              </TableFooter>
            )}
          </Table>
        </>
      )}
    </ReportView>
  );
}
