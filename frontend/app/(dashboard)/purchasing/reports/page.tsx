"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { SortableTableHead } from "@/components/erp/report-view/sortable-table-head";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { reportingApi } from "@/features/reporting/api/client";
import { formatCurrency } from "@/lib/format-currency";
import { reportExportHandlers } from "@/lib/report-export";
import { useSortedRows } from "@/lib/use-sorted-rows";
import type { PurchaseByVendorRow } from "@/features/reporting/api/types";

const ALL_SUPPLIERS = "__all__";

function ByVendorTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [partnerId, setPartnerId] = useState(ALL_SUPPLIERS);
  const [ranAt, setRanAt] = useState<{ from: string; to: string; partner?: string } | null>(null);

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "vendors"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });
  const reportQuery = useQuery({
    queryKey: ["purchases-by-supplier", companyId, ranAt?.from, ranAt?.to, ranAt?.partner],
    queryFn: () => reportingApi.purchasesBySupplier(companyId, ranAt!.from, ranAt!.to, ranAt?.partner),
    enabled: !!ranAt,
  });

  const rows: PurchaseByVendorRow[] = reportQuery.data ?? [];

  const totals = rows.reduce(
    (acc, r) => ({
      bill_count: acc.bill_count + r.bill_count,
      subtotal: acc.subtotal + Number(r.subtotal),
      tax_amount: acc.tax_amount + Number(r.tax_amount),
      total: acc.total + Number(r.total),
      adjustments: acc.adjustments + Number(r.adjustments),
      net_total: acc.net_total + Number(r.net_total),
      payments_made: acc.payments_made + Number(r.payments_made),
      balance: acc.balance + Number(r.balance),
    }),
    { bill_count: 0, subtotal: 0, tax_amount: 0, total: 0, adjustments: 0, net_total: 0, payments_made: 0, balance: 0 }
  );
  const { sort, toggleSort, sortedRows } = useSortedRows(rows, {
    partner_name: (r) => r.partner_name,
    bill_count: (r) => r.bill_count,
    subtotal: (r) => Number(r.subtotal),
    tax_amount: (r) => Number(r.tax_amount),
    total: (r) => Number(r.total),
    adjustments: (r) => Number(r.adjustments),
    net_total: (r) => Number(r.net_total),
    payments_made: (r) => Number(r.payments_made),
    balance: (r) => Number(r.balance),
  });
  const displayRows = sortedRows ?? rows;

  return (
    <ReportView
      title={t("purchasing.reports.tab.by_supplier")}
      filterArea={
        <>
          <div className="w-64 space-y-1">
            <Label className="text-xs">{t("purchasing.reports.select_supplier")}</Label>
            <Select value={partnerId} onValueChange={(v) => setPartnerId((v as string) ?? ALL_SUPPLIERS)}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("purchasing.reports.select_supplier")}>
                  {(value: string) =>
                    value === ALL_SUPPLIERS
                      ? t("purchasing.reports.all_suppliers")
                      : (partnersQuery.data?.find((p) => p.id === value)?.name ?? value)
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_SUPPLIERS}>{t("purchasing.reports.all_suppliers")}</SelectItem>
                {partnersQuery.data?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">{t("sales.reports.date_from")}</Label>
            <Input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="h-8 w-40 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">{t("sales.reports.date_to")}</Label>
            <Input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="h-8 w-40 text-sm"
            />
          </div>
        </>
      }
      onApply={() =>
        setRanAt({ from: dateFrom, to: dateTo, partner: partnerId === ALL_SUPPLIERS ? undefined : partnerId })
      }
      onReset={() => setRanAt(null)}
      onPrint={ranAt && rows.length > 0 ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/reporting/purchasing/by-supplier",
            { date_from: ranAt.from, date_to: ranAt.to, ...(ranAt.partner ? { partner_id: ranAt.partner } : {}), lang: locale },
            companyId
          )
        : {})}
      isLoading={reportQuery.isFetching}
      isError={reportQuery.isError}
      errorMessage={String(reportQuery.error ?? "")}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!ranAt && !reportQuery.isFetching && rows.length === 0}
      kpis={
        ranAt && rows.length > 0
          ? [
              { label: t("purchasing.reports.supplier.partner_name"), value: String(rows.length) },
              { label: t("purchasing.reports.supplier.bill_count"), value: String(totals.bill_count) },
              { label: t("sales.reports.grand_total"), value: formatCurrency(totals.total) },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("sales.reports.run_hint")}</p>}
      {ranAt && rows.length > 0 && (
        <>
          <ReportPrintHeader
            reportTitle={t("purchasing.reports.tab.by_supplier")}
            dateRangeLabel={`${ranAt.from} – ${ranAt.to}`}
          />
          <Table>
            <TableHeader>
              <TableRow>
                <SortableTableHead sortKey="partner_name" sort={sort} onSort={toggleSort}>
                  {t("purchasing.reports.supplier.partner_name")}
                </SortableTableHead>
                <SortableTableHead sortKey="bill_count" sort={sort} onSort={toggleSort} align="end">
                  {t("purchasing.reports.supplier.bill_count")}
                </SortableTableHead>
                <SortableTableHead sortKey="subtotal" sort={sort} onSort={toggleSort} align="end">
                  {t("purchasing.reports.supplier.subtotal")}
                </SortableTableHead>
                <SortableTableHead sortKey="tax_amount" sort={sort} onSort={toggleSort} align="end">
                  {t("purchasing.reports.supplier.tax")}
                </SortableTableHead>
                <SortableTableHead sortKey="total" sort={sort} onSort={toggleSort} align="end" className="font-semibold">
                  {t("purchasing.reports.supplier.total")}
                </SortableTableHead>
                <SortableTableHead sortKey="adjustments" sort={sort} onSort={toggleSort} align="end">
                  {t("purchasing.reports.supplier.adjustments")}
                </SortableTableHead>
                <SortableTableHead sortKey="net_total" sort={sort} onSort={toggleSort} align="end" className="font-semibold">
                  {t("purchasing.reports.supplier.net_total")}
                </SortableTableHead>
                <SortableTableHead sortKey="payments_made" sort={sort} onSort={toggleSort} align="end">
                  {t("purchasing.reports.supplier.payments_made")}
                </SortableTableHead>
                <SortableTableHead sortKey="balance" sort={sort} onSort={toggleSort} align="end" className="font-semibold">
                  {t("purchasing.reports.supplier.balance")}
                </SortableTableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {displayRows.map((row) => (
                <TableRow key={row.partner_id}>
                  <TableCell className="font-medium">
                    <Link
                      href={`/accounting?tab=vendor-subledger&partner=${row.partner_id}`}
                      className="underline-offset-4 hover:underline"
                    >
                      {row.partner_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-end tabular-nums">{row.bill_count}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.subtotal)}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.tax_amount)}</TableCell>
                  <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(row.total)}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.adjustments)}</TableCell>
                  <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(row.net_total)}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.payments_made)}</TableCell>
                  <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(row.balance)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell colSpan={1} className="font-bold">{t("sales.reports.totals")}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{totals.bill_count}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.subtotal)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.tax_amount)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.total)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.adjustments)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.net_total)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.payments_made)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.balance)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </>
      )}
    </ReportView>
  );
}

export default function PurchasingReportsPage() {
  const { t } = useI18n();

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("purchasing.reports.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("purchasing.reports.description")}</p>
      </div>

      <ByVendorTab />
    </div>
  );
}
