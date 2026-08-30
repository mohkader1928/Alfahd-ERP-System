"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/erp/states/empty-state";
import { SortableTableHead } from "@/components/erp/report-view/sortable-table-head";
import { useI18n } from "@/lib/i18n/config";
import { formatCurrency } from "@/lib/format-currency";
import { useSortedRows } from "@/lib/use-sorted-rows";
import type { RepresentativePerformanceRow } from "@/features/reporting/api/types";

/** Commercial Performance Stage 3 (Part B): the Dashboard's ranked
 * Representative Performance table. Sorted by Net Sales by default (the
 * backend already returns rows in that order); Collections and Net
 * Commission are explicitly also sortable per spec, along with every other
 * numeric column for consistency with the rest of this app's report
 * tables. Zero-activity representatives are rendered plainly (never
 * hidden), and the "Unattributed / Legacy" row is styled distinctly and
 * never links anywhere — there is no representative record behind it. */
export function RepresentativePerformanceTable({ rows }: { rows: RepresentativePerformanceRow[] }) {
  const { t } = useI18n();

  const { sort, toggleSort, sortedRows } = useSortedRows(rows, {
    representative_name: (r) => r.representative_name,
    gross_sales: (r) => Number(r.gross_sales),
    returns: (r) => Number(r.returns),
    net_sales: (r) => Number(r.net_sales),
    collections: (r) => Number(r.collections),
    sales_commission: (r) => Number(r.sales_commission),
    collection_commission: (r) => Number(r.collection_commission),
    net_commission: (r) => Number(r.net_commission),
  });
  // Default order (no user sort yet): the backend's own net_sales-desc
  // ordering, which is already "sorted by Net Sales by default".
  const displayRows = sortedRows ?? rows;

  if (rows.length === 0) {
    return <EmptyState title={t("dashboard.commercial.representative_table.empty")} />;
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">{t("dashboard.commercial.representative_table.rank")}</TableHead>
            <SortableTableHead sortKey="representative_name" sort={sort} onSort={toggleSort}>
              {t("dashboard.commercial.representative_table.representative")}
            </SortableTableHead>
            <SortableTableHead sortKey="gross_sales" sort={sort} onSort={toggleSort} align="end">
              {t("dashboard.commercial.representative_table.gross_sales")}
            </SortableTableHead>
            <SortableTableHead sortKey="returns" sort={sort} onSort={toggleSort} align="end">
              {t("dashboard.commercial.representative_table.returns")}
            </SortableTableHead>
            <SortableTableHead sortKey="net_sales" sort={sort} onSort={toggleSort} align="end" className="font-semibold">
              {t("dashboard.commercial.representative_table.net_sales")}
            </SortableTableHead>
            <SortableTableHead sortKey="collections" sort={sort} onSort={toggleSort} align="end">
              {t("dashboard.commercial.representative_table.collections")}
            </SortableTableHead>
            <SortableTableHead sortKey="sales_commission" sort={sort} onSort={toggleSort} align="end">
              {t("dashboard.commercial.representative_table.sales_commission")}
            </SortableTableHead>
            <SortableTableHead sortKey="collection_commission" sort={sort} onSort={toggleSort} align="end">
              {t("dashboard.commercial.representative_table.collection_commission")}
            </SortableTableHead>
            <SortableTableHead sortKey="net_commission" sort={sort} onSort={toggleSort} align="end" className="font-semibold">
              {t("dashboard.commercial.representative_table.net_commission")}
            </SortableTableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {displayRows.map((row, index) => (
            <TableRow key={row.representative_id ?? "unattributed"}>
              <TableCell className="text-muted-foreground tabular-nums">{index + 1}</TableCell>
              <TableCell className="font-medium">
                {row.is_unattributed || !row.representative_id ? (
                  <span className="inline-flex items-center gap-2 text-muted-foreground italic">
                    {row.representative_name}
                    <Badge variant="secondary">{t("dashboard.commercial.representative_table.unattributed_badge")}</Badge>
                  </span>
                ) : (
                  <Link
                    href={`/master-data/sales-representatives/${row.representative_id}`}
                    className="underline-offset-4 hover:underline"
                  >
                    {row.representative_name}
                  </Link>
                )}
              </TableCell>
              <TableCell className="text-end tabular-nums">{formatCurrency(row.gross_sales)}</TableCell>
              <TableCell className="text-end tabular-nums">{formatCurrency(row.returns)}</TableCell>
              <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(row.net_sales)}</TableCell>
              <TableCell className="text-end tabular-nums">{formatCurrency(row.collections)}</TableCell>
              <TableCell className="text-end tabular-nums">{formatCurrency(row.sales_commission)}</TableCell>
              <TableCell className="text-end tabular-nums">{formatCurrency(row.collection_commission)}</TableCell>
              <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(row.net_commission)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
