"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { SortableTableHead } from "@/components/erp/report-view/sortable-table-head";
import { DateRangePresetFilter, computePresetRange } from "@/components/erp/report-view/date-range-preset-filter";
import { ErrorState } from "@/components/erp/states/error-state";
import { NotFoundState } from "@/components/erp/states/not-found";
import { PermissionDenied } from "@/components/erp/states/permission-denied";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { reportingApi } from "@/features/reporting/api/client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { useSortedRows } from "@/lib/use-sorted-rows";
import { ApiError } from "@/lib/api-client";
import type { SalesRepresentative } from "@/features/identity/api/types";

export default function SalesRepresentativePerformancePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const repQuery = useQuery({
    queryKey: ["sales-representative", companyId, id],
    queryFn: () => identityApi.getSalesRepresentative(companyId, id),
  });

  if (repQuery.isError && repQuery.error instanceof ApiError && repQuery.error.status === 404) {
    return <NotFoundState label={t("master_data.sales_representatives.not_found")} />;
  }
  if (repQuery.isError && repQuery.error instanceof ApiError && repQuery.error.status === 403) {
    return <PermissionDenied />;
  }
  if (repQuery.isError) {
    return <ErrorState onRetry={() => repQuery.refetch()} />;
  }
  if (repQuery.isLoading || !repQuery.data) {
    return null;
  }

  return <RepresentativePerformance rep={repQuery.data} companyId={companyId} />;
}

function RepresentativePerformance({ rep, companyId }: { rep: SalesRepresentative; companyId: string }) {
  const { t } = useI18n();
  const initialRange = computePresetRange("current_month");
  const [dateFrom, setDateFrom] = useState(initialRange.from);
  const [dateTo, setDateTo] = useState(initialRange.to);
  const [ranAt, setRanAt] = useState<{ from: string; to: string } | null>(initialRange
    ? { from: initialRange.from, to: initialRange.to }
    : null
  );

  const perfQuery = useQuery({
    queryKey: ["representative-performance", companyId, rep.id, ranAt?.from, ranAt?.to],
    queryFn: () => reportingApi.commercialRepresentativePerformance(companyId, rep.id, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  // Stage 3 Phase 4: Representative -> Customer -> Invoice drill-down —
  // each customer row links into the Sales Invoices list, pre-filtered to
  // this customer AND this representative.
  const customersQuery = useQuery({
    queryKey: ["representative-customers", companyId, rep.id, ranAt?.from, ranAt?.to],
    queryFn: () => reportingApi.commercialRepresentativeCustomers(companyId, rep.id, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });
  const customerRows = customersQuery.data ?? [];
  const customersSort = useSortedRows(customerRows, {
    partner_name: (r) => r.partner_name,
    invoice_count: (r) => r.invoice_count,
    gross_sales: (r) => Number(r.gross_sales),
    returns: (r) => Number(r.returns),
    net_sales: (r) => Number(r.net_sales),
  });
  const displayCustomerRows = customersSort.sortedRows ?? customerRows;

  const summary = perfQuery.data?.summary;
  const salesLines = perfQuery.data?.sales_lines ?? [];
  const returnsLines = perfQuery.data?.returns_lines ?? [];
  const collectionsLines = perfQuery.data?.collections_lines ?? [];

  const salesSort = useSortedRows(salesLines, {
    invoice_number: (r) => r.invoice_number,
    invoice_date: (r) => r.invoice_date,
    customer_name: (r) => r.customer_name,
    sales_amount: (r) => Number(r.sales_amount),
    commission_amount: (r) => Number(r.commission_amount),
  });
  const displaySalesLines = salesSort.sortedRows ?? salesLines;

  const returnsSort = useSortedRows(returnsLines, {
    credit_note_number: (r) => r.credit_note_number,
    credit_note_date: (r) => r.credit_note_date,
    customer_name: (r) => r.customer_name,
    return_amount: (r) => Number(r.return_amount),
    commission_amount: (r) => Number(r.commission_amount),
  });
  const displayReturnsLines = returnsSort.sortedRows ?? returnsLines;

  const collectionsSort = useSortedRows(collectionsLines, {
    payment_number: (r) => r.payment_number,
    payment_date: (r) => r.payment_date,
    customer_name: (r) => r.customer_name,
    collection_amount: (r) => Number(r.collection_amount),
    commission_amount: (r) => Number(r.commission_amount),
  });
  const displayCollectionsLines = collectionsSort.sortedRows ?? collectionsLines;

  const salesTotal = salesLines.reduce((acc, r) => acc + Number(r.sales_amount), 0);
  const salesCommissionTotal = salesLines.reduce((acc, r) => acc + Number(r.commission_amount), 0);
  const returnsTotal = returnsLines.reduce((acc, r) => acc + Number(r.return_amount), 0);
  const returnsCommissionTotal = returnsLines.reduce((acc, r) => acc + Number(r.commission_amount), 0);
  const collectionsTotal = collectionsLines.reduce((acc, r) => acc + Number(r.collection_amount), 0);
  const collectionsCommissionTotal = collectionsLines.reduce((acc, r) => acc + Number(r.commission_amount), 0);

  const hasAnyRows =
    salesLines.length > 0 || returnsLines.length > 0 || collectionsLines.length > 0 || customerRows.length > 0;

  return (
    <ReportView
      title={rep.name}
      description={`${rep.code} · ${t("master_data.sales_representatives.performance_title")}`}
      breadcrumbs={[
        { label: t("nav.master_data") },
        { label: t("master_data.sales_representatives.title"), href: "/master-data/sales-representatives" },
        { label: rep.name },
      ]}
      filterArea={
        <div className="flex flex-wrap items-end gap-4">
          <DateRangePresetFilter dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo} />
          <Badge variant={rep.is_active ? "outline" : "destructive"}>
            {rep.is_active ? t("common.active") : t("common.inactive")}
          </Badge>
        </div>
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo })}
      onReset={() => setRanAt(null)}
      onPrint={ranAt ? () => window.print() : undefined}
      isLoading={perfQuery.isFetching}
      isError={perfQuery.isError}
      errorMessage={String(perfQuery.error ?? "")}
      onRetry={() => perfQuery.refetch()}
      isEmpty={!!ranAt && !perfQuery.isFetching && !hasAnyRows}
      kpis={
        ranAt && summary
          ? [
              { label: t("master_data.sales_representatives.perf.gross_sales"), value: formatCurrency(summary.gross_sales) },
              { label: t("master_data.sales_representatives.perf.returns"), value: formatCurrency(summary.returns) },
              { label: t("master_data.sales_representatives.perf.net_sales"), value: formatCurrency(summary.net_sales) },
              { label: t("master_data.sales_representatives.perf.collections"), value: formatCurrency(summary.collections) },
              { label: t("master_data.sales_representatives.perf.sales_commission"), value: formatCurrency(summary.sales_commission) },
              {
                label: t("master_data.sales_representatives.perf.collection_commission"),
                value: formatCurrency(summary.collection_commission),
              },
              { label: t("master_data.sales_representatives.perf.net_commission"), value: formatCurrency(summary.net_commission) },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("sales.reports.run_hint")}</p>}
      {ranAt && hasAnyRows && (
        <div className="space-y-8">
          <ReportPrintHeader
            reportTitle={`${rep.name} — ${t("master_data.sales_representatives.performance_title")}`}
            dateRangeLabel={`${ranAt.from} – ${ranAt.to}`}
          />

          <section className="space-y-2">
            <h2 className="text-sm font-semibold">{t("master_data.sales_representatives.perf.customers")}</h2>
            {customerRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("common.empty")}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableTableHead sortKey="partner_name" sort={customersSort.sort} onSort={customersSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.customer")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="invoice_count" sort={customersSort.sort} onSort={customersSort.toggleSort} align="end">
                      {t("master_data.sales_representatives.perf.invoice_count")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="gross_sales" sort={customersSort.sort} onSort={customersSort.toggleSort} align="end">
                      {t("master_data.sales_representatives.perf.gross_sales")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="returns" sort={customersSort.sort} onSort={customersSort.toggleSort} align="end">
                      {t("master_data.sales_representatives.perf.returns")}
                    </SortableTableHead>
                    <SortableTableHead
                      sortKey="net_sales"
                      sort={customersSort.sort}
                      onSort={customersSort.toggleSort}
                      align="end"
                      className="font-semibold"
                    >
                      {t("master_data.sales_representatives.perf.net_sales")}
                    </SortableTableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displayCustomerRows.map((row) => (
                    <TableRow key={row.partner_id}>
                      <TableCell className="font-medium">
                        <Link
                          href={`/sales/invoices?partner_id=${row.partner_id}&sales_rep_id=${rep.id}`}
                          className="underline-offset-4 hover:underline"
                        >
                          {row.partner_name}
                        </Link>
                      </TableCell>
                      <TableCell className="text-end tabular-nums">{row.invoice_count}</TableCell>
                      <TableCell className="text-end tabular-nums">{formatCurrency(row.gross_sales)}</TableCell>
                      <TableCell className="text-end tabular-nums">{formatCurrency(row.returns)}</TableCell>
                      <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(row.net_sales)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold">{t("master_data.sales_representatives.perf.sales_analysis")}</h2>
            {salesLines.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("common.empty")}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableTableHead sortKey="invoice_number" sort={salesSort.sort} onSort={salesSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.invoice_number")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="invoice_date" sort={salesSort.sort} onSort={salesSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.invoice_date")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="customer_name" sort={salesSort.sort} onSort={salesSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.customer")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="sales_amount" sort={salesSort.sort} onSort={salesSort.toggleSort} align="end">
                      {t("master_data.sales_representatives.perf.sales_amount")}
                    </SortableTableHead>
                    <TableHead className="text-end">{t("master_data.sales_representatives.perf.commission_rate")}</TableHead>
                    <SortableTableHead
                      sortKey="commission_amount"
                      sort={salesSort.sort}
                      onSort={salesSort.toggleSort}
                      align="end"
                      className="font-semibold"
                    >
                      {t("master_data.sales_representatives.perf.commission_amount")}
                    </SortableTableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displaySalesLines.map((line) => (
                    <TableRow key={line.invoice_id}>
                      <TableCell className="font-medium">
                        <Link href={`/sales/invoices/${line.invoice_id}`} className="underline-offset-4 hover:underline">
                          {line.invoice_number}
                        </Link>
                      </TableCell>
                      <TableCell>{formatDate(line.invoice_date)}</TableCell>
                      <TableCell>{line.customer_name}</TableCell>
                      <TableCell className="text-end tabular-nums">{formatCurrency(line.sales_amount)}</TableCell>
                      <TableCell className="text-end tabular-nums">{line.commission_rate ? `${line.commission_rate}%` : "—"}</TableCell>
                      <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(line.commission_amount)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                <TableFooter>
                  <TableRow>
                    <TableCell colSpan={3} className="font-bold">
                      {t("sales.reports.totals")}
                    </TableCell>
                    <TableCell className="text-end font-bold tabular-nums">{formatCurrency(salesTotal)}</TableCell>
                    <TableCell />
                    <TableCell className="text-end font-bold tabular-nums">{formatCurrency(salesCommissionTotal)}</TableCell>
                  </TableRow>
                </TableFooter>
              </Table>
            )}
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold">{t("master_data.sales_representatives.perf.returns_analysis")}</h2>
            {returnsLines.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("common.empty")}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableTableHead sortKey="credit_note_number" sort={returnsSort.sort} onSort={returnsSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.credit_note_number")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="credit_note_date" sort={returnsSort.sort} onSort={returnsSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.credit_note_date")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="customer_name" sort={returnsSort.sort} onSort={returnsSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.customer")}
                    </SortableTableHead>
                    <TableHead>{t("master_data.sales_representatives.perf.original_invoice")}</TableHead>
                    <SortableTableHead sortKey="return_amount" sort={returnsSort.sort} onSort={returnsSort.toggleSort} align="end">
                      {t("master_data.sales_representatives.perf.return_amount")}
                    </SortableTableHead>
                    <TableHead className="text-end">{t("master_data.sales_representatives.perf.historical_commission_rate")}</TableHead>
                    <SortableTableHead
                      sortKey="commission_amount"
                      sort={returnsSort.sort}
                      onSort={returnsSort.toggleSort}
                      align="end"
                      className="font-semibold"
                    >
                      {t("master_data.sales_representatives.perf.negative_commission_amount")}
                    </SortableTableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displayReturnsLines.map((line) => (
                    <TableRow key={line.credit_note_id}>
                      <TableCell className="font-medium">
                        <Link href={`/sales/invoices/${line.credit_note_id}`} className="underline-offset-4 hover:underline">
                          {line.credit_note_number}
                        </Link>
                      </TableCell>
                      <TableCell>{formatDate(line.credit_note_date)}</TableCell>
                      <TableCell>{line.customer_name}</TableCell>
                      <TableCell className="text-muted-foreground">{line.original_invoice_number ?? "—"}</TableCell>
                      <TableCell className="text-end tabular-nums">{formatCurrency(line.return_amount)}</TableCell>
                      <TableCell className="text-end tabular-nums">{line.commission_rate ? `${line.commission_rate}%` : "—"}</TableCell>
                      <TableCell className="text-end tabular-nums font-semibold text-destructive">
                        {formatCurrency(line.commission_amount)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                <TableFooter>
                  <TableRow>
                    <TableCell colSpan={4} className="font-bold">
                      {t("sales.reports.totals")}
                    </TableCell>
                    <TableCell className="text-end font-bold tabular-nums">{formatCurrency(returnsTotal)}</TableCell>
                    <TableCell />
                    <TableCell className="text-end font-bold tabular-nums">{formatCurrency(returnsCommissionTotal)}</TableCell>
                  </TableRow>
                </TableFooter>
              </Table>
            )}
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold">{t("master_data.sales_representatives.perf.collections_analysis")}</h2>
            {collectionsLines.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("common.empty")}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableTableHead sortKey="payment_number" sort={collectionsSort.sort} onSort={collectionsSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.payment_number")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="payment_date" sort={collectionsSort.sort} onSort={collectionsSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.payment_date")}
                    </SortableTableHead>
                    <SortableTableHead sortKey="customer_name" sort={collectionsSort.sort} onSort={collectionsSort.toggleSort}>
                      {t("master_data.sales_representatives.perf.customer")}
                    </SortableTableHead>
                    <SortableTableHead
                      sortKey="collection_amount"
                      sort={collectionsSort.sort}
                      onSort={collectionsSort.toggleSort}
                      align="end"
                    >
                      {t("master_data.sales_representatives.perf.collection_amount")}
                    </SortableTableHead>
                    <TableHead className="text-end">{t("master_data.sales_representatives.perf.commission_rate")}</TableHead>
                    <SortableTableHead
                      sortKey="commission_amount"
                      sort={collectionsSort.sort}
                      onSort={collectionsSort.toggleSort}
                      align="end"
                      className="font-semibold"
                    >
                      {t("master_data.sales_representatives.perf.commission_amount")}
                    </SortableTableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displayCollectionsLines.map((line) => (
                    <TableRow key={line.payment_id}>
                      <TableCell className="font-medium">
                        <Link href={`/payments/${line.payment_id}`} className="underline-offset-4 hover:underline">
                          {line.payment_number}
                        </Link>
                      </TableCell>
                      <TableCell>{formatDate(line.payment_date)}</TableCell>
                      <TableCell>{line.customer_name}</TableCell>
                      <TableCell className="text-end tabular-nums">{formatCurrency(line.collection_amount)}</TableCell>
                      <TableCell className="text-end tabular-nums">{line.commission_rate ? `${line.commission_rate}%` : "—"}</TableCell>
                      <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(line.commission_amount)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                <TableFooter>
                  <TableRow>
                    <TableCell colSpan={3} className="font-bold">
                      {t("sales.reports.totals")}
                    </TableCell>
                    <TableCell className="text-end font-bold tabular-nums">{formatCurrency(collectionsTotal)}</TableCell>
                    <TableCell />
                    <TableCell className="text-end font-bold tabular-nums">{formatCurrency(collectionsCommissionTotal)}</TableCell>
                  </TableRow>
                </TableFooter>
              </Table>
            )}
          </section>
        </div>
      )}
    </ReportView>
  );
}
