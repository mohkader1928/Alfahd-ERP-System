"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { fixedAssetsApi } from "@/features/fixed-assets/api/client";
import { formatCurrency } from "@/lib/format-currency";
import { reportExportHandlers } from "@/lib/report-export";

/** Owner-standing requirement: the fixed asset register must always tie
 * out to the same GL accounts Trial Balance reads — this is the same
 * discipline already applied to AR/AP (customer/vendor subledger vs
 * Trial Balance). Each row compares the register's own sum for one GL
 * account against that account's real posted balance. */
export function FixedAssetsReconciliationTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const [asOfDate, setAsOfDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<string | null>(null);

  const reportQuery = useQuery({
    queryKey: ["fixed-assets-reconciliation", companyId, ranAt],
    queryFn: () => fixedAssetsApi.getReconciliation(companyId, ranAt!),
    enabled: !!ranAt,
  });
  const r = reportQuery.data;

  return (
    <ReportView
      title={t("fixed_assets.reconciliation.title")}
      filterArea={
        <div className="space-y-1">
          <Label className="text-xs">{t("fixed_assets.reconciliation.as_of_date")}</Label>
          <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-40" />
        </div>
      }
      onApply={() => setRanAt(asOfDate)}
      onPrint={r ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers("/api/v1/fixed-assets/reconciliation", { as_of_date: ranAt, lang: locale }, companyId)
        : {})}
      isLoading={reportQuery.isLoading}
      isError={reportQuery.isError}
      onRetry={() => reportQuery.refetch()}
      kpis={
        r
          ? [
              { label: t("fixed_assets.cost"), value: formatCurrency(r.total_register_cost) },
              {
                label: t("fixed_assets.accumulated_depreciation"),
                value: formatCurrency(r.total_register_accumulated_depreciation),
              },
              { label: t("fixed_assets.net_book_value"), value: formatCurrency(r.total_register_net_book_value) },
              {
                label: t("fixed_assets.depreciation_expense"),
                value: formatCurrency(r.total_register_depreciation_expense),
              },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("fixed_assets.reconciliation.hint")}</p>}
      {ranAt && r && (
        <>
          <ReportPrintHeader reportTitle={t("fixed_assets.reconciliation.title")} dateRangeLabel={r.as_of_date} />
          <div className="mb-3">
            <Badge variant={r.fully_matched ? "default" : "destructive"}>
              {r.fully_matched
                ? t("fixed_assets.reconciliation.matched")
                : t("fixed_assets.reconciliation.mismatched")}
            </Badge>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("accounting.accounts.code")}</TableHead>
                <TableHead>{t("accounting.accounts.name")}</TableHead>
                <TableHead className="text-end">{t("fixed_assets.reconciliation.register_total")}</TableHead>
                <TableHead className="text-end">{t("fixed_assets.reconciliation.gl_balance")}</TableHead>
                <TableHead className="text-end">{t("fixed_assets.reconciliation.difference")}</TableHead>
                <TableHead>{t("fixed_assets.status")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {r.accounts.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    {t("common.empty")}
                  </TableCell>
                </TableRow>
              )}
              {r.accounts.map((row) => (
                <TableRow key={row.account_id}>
                  <TableCell className="font-mono">{row.account_code}</TableCell>
                  <TableCell>{row.account_name}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(row.register_total)}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(row.gl_balance)}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(row.difference)}</TableCell>
                  <TableCell>
                    <Badge variant={row.matches ? "default" : "destructive"}>
                      {row.matches
                        ? t("fixed_assets.reconciliation.matched")
                        : t("fixed_assets.reconciliation.mismatched")}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            {r.accounts.length > 0 && (
              <TableFooter>
                <TableRow className="font-semibold">
                  <TableCell colSpan={2}>{t("fixed_assets.net_book_value")}</TableCell>
                  <TableCell className="text-end font-mono">{formatCurrency(r.total_register_cost)}</TableCell>
                  <TableCell />
                  <TableCell className="text-end font-mono">{formatCurrency(r.total_register_net_book_value)}</TableCell>
                  <TableCell />
                </TableRow>
              </TableFooter>
            )}
          </Table>
        </>
      )}
    </ReportView>
  );
}
