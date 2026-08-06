"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { reportingApi } from "@/features/reporting/api/client";
import { formatCurrency } from "@/lib/format-currency";
import type {
  SalesByCustomerRow,
  SalesByPeriodRow,
  SalesByProductRow,
} from "@/features/reporting/api/types";

// ── Shared filter state ───────────────────────────────────────────────────────

function useDateRange() {
  const [dateFrom, setDateFrom] = useState(
    () => new Date().toISOString().slice(0, 8) + "01"
  );
  const [dateTo, setDateTo] = useState(
    () => new Date().toISOString().slice(0, 10)
  );
  return { dateFrom, setDateFrom, dateTo, setDateTo };
}

// ── Filter area (shared across tabs) ─────────────────────────────────────────

function DateRangeFilter({
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
}: {
  dateFrom: string;
  setDateFrom: (v: string) => void;
  dateTo: string;
  setDateTo: (v: string) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap gap-4">
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
    </div>
  );
}

// ── Tab: By Customer ──────────────────────────────────────────────────────────

function ByCustomerTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { dateFrom, setDateFrom, dateTo, setDateTo } = useDateRange();
  const [ranAt, setRanAt] = useState<{ from: string; to: string } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["sales-by-customer", companyId, ranAt?.from, ranAt?.to],
    queryFn: () => reportingApi.salesByCustomer(companyId, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  const rows: SalesByCustomerRow[] = reportQuery.data ?? [];

  const totals = rows.reduce(
    (acc, r) => ({
      invoice_count: acc.invoice_count + r.invoice_count,
      subtotal: acc.subtotal + Number(r.subtotal),
      tax_amount: acc.tax_amount + Number(r.tax_amount),
      total: acc.total + Number(r.total),
    }),
    { invoice_count: 0, subtotal: 0, tax_amount: 0, total: 0 }
  );

  return (
    <ReportView
      title={t("sales.reports.tab.by_customer")}
      filterArea={
        <DateRangeFilter
          dateFrom={dateFrom}
          setDateFrom={setDateFrom}
          dateTo={dateTo}
          setDateTo={setDateTo}
        />
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo })}
      onReset={() => setRanAt(null)}
      onPrint={ranAt && rows.length > 0 ? () => window.print() : undefined}
      isLoading={reportQuery.isFetching}
      isError={reportQuery.isError}
      errorMessage={String(reportQuery.error ?? "")}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!ranAt && !reportQuery.isFetching && rows.length === 0}
      kpis={
        ranAt && rows.length > 0
          ? [
              { label: t("sales.reports.customer.partner_name"), value: String(rows.length) },
              { label: t("sales.reports.customer.invoice_count"), value: String(totals.invoice_count) },
              { label: t("sales.reports.grand_total"), value: formatCurrency(totals.total) },
            ]
          : undefined
      }
    >
      {!ranAt && (
        <p className="text-sm text-muted-foreground">{t("sales.reports.run_hint")}</p>
      )}
      {ranAt && rows.length > 0 && (
        <>
          <ReportPrintHeader
            reportTitle={t("sales.reports.tab.by_customer")}
            dateRangeLabel={`${ranAt.from} – ${ranAt.to}`}
          />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("sales.reports.customer.partner_name")}</TableHead>
                <TableHead className="text-end">{t("sales.reports.customer.invoice_count")}</TableHead>
                <TableHead className="text-end">{t("sales.reports.customer.subtotal")}</TableHead>
                <TableHead className="text-end">{t("sales.reports.customer.tax")}</TableHead>
                <TableHead className="text-end font-semibold">{t("sales.reports.customer.total")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.partner_id}>
                  <TableCell className="font-medium">{row.partner_name}</TableCell>
                  <TableCell className="text-end tabular-nums">{row.invoice_count}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.subtotal)}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.tax_amount)}</TableCell>
                  <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(row.total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell colSpan={1} className="font-bold">{t("sales.reports.totals")}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{totals.invoice_count}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.subtotal)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.tax_amount)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.total)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </>
      )}
    </ReportView>
  );
}

// ── Tab: By Product ───────────────────────────────────────────────────────────

function ByProductTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { dateFrom, setDateFrom, dateTo, setDateTo } = useDateRange();
  const [ranAt, setRanAt] = useState<{ from: string; to: string } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["sales-by-product", companyId, ranAt?.from, ranAt?.to],
    queryFn: () => reportingApi.salesByProduct(companyId, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  const rows: SalesByProductRow[] = reportQuery.data ?? [];

  const totals = rows.reduce(
    (acc, r) => ({
      qty_sold: acc.qty_sold + Number(r.qty_sold),
      subtotal: acc.subtotal + Number(r.subtotal),
      tax_amount: acc.tax_amount + Number(r.tax_amount),
      total: acc.total + Number(r.total),
    }),
    { qty_sold: 0, subtotal: 0, tax_amount: 0, total: 0 }
  );

  return (
    <ReportView
      title={t("sales.reports.tab.by_product")}
      filterArea={
        <DateRangeFilter
          dateFrom={dateFrom}
          setDateFrom={setDateFrom}
          dateTo={dateTo}
          setDateTo={setDateTo}
        />
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo })}
      onReset={() => setRanAt(null)}
      onPrint={ranAt && rows.length > 0 ? () => window.print() : undefined}
      isLoading={reportQuery.isFetching}
      isError={reportQuery.isError}
      errorMessage={String(reportQuery.error ?? "")}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!ranAt && !reportQuery.isFetching && rows.length === 0}
      kpis={
        ranAt && rows.length > 0
          ? [
              { label: t("sales.reports.product.product_name"), value: String(rows.length) },
              { label: t("sales.reports.product.qty_sold"), value: totals.qty_sold.toFixed(2) },
              { label: t("sales.reports.grand_total"), value: formatCurrency(totals.total) },
            ]
          : undefined
      }
    >
      {!ranAt && (
        <p className="text-sm text-muted-foreground">{t("sales.reports.run_hint")}</p>
      )}
      {ranAt && rows.length > 0 && (
        <>
          <ReportPrintHeader
            reportTitle={t("sales.reports.tab.by_product")}
            dateRangeLabel={`${ranAt.from} – ${ranAt.to}`}
          />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("sales.reports.product.product_code")}</TableHead>
                <TableHead>{t("sales.reports.product.product_name")}</TableHead>
                <TableHead className="text-end">{t("sales.reports.product.qty_sold")}</TableHead>
                <TableHead className="text-end">{t("sales.reports.product.subtotal")}</TableHead>
                <TableHead className="text-end">{t("sales.reports.product.tax")}</TableHead>
                <TableHead className="text-end font-semibold">{t("sales.reports.product.total")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.product_id}>
                  <TableCell className="font-mono text-xs text-muted-foreground">{row.product_code || "—"}</TableCell>
                  <TableCell className="font-medium">{row.product_name}</TableCell>
                  <TableCell className="text-end tabular-nums">{Number(row.qty_sold).toFixed(2)}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.subtotal)}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.tax_amount)}</TableCell>
                  <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(row.total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell colSpan={2} className="font-bold">{t("sales.reports.totals")}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{totals.qty_sold.toFixed(2)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.subtotal)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.tax_amount)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.total)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </>
      )}
    </ReportView>
  );
}

// ── Tab: By Period ────────────────────────────────────────────────────────────

function ByPeriodTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { dateFrom, setDateFrom, dateTo, setDateTo } = useDateRange();
  const [ranAt, setRanAt] = useState<{ from: string; to: string } | null>(null);

  const reportQuery = useQuery({
    queryKey: ["sales-by-period", companyId, ranAt?.from, ranAt?.to],
    queryFn: () => reportingApi.salesByPeriod(companyId, ranAt!.from, ranAt!.to),
    enabled: !!ranAt,
  });

  const rows: SalesByPeriodRow[] = reportQuery.data ?? [];

  const totals = rows.reduce(
    (acc, r) => ({
      invoice_count: acc.invoice_count + r.invoice_count,
      subtotal: acc.subtotal + Number(r.subtotal),
      tax_amount: acc.tax_amount + Number(r.tax_amount),
      total: acc.total + Number(r.total),
    }),
    { invoice_count: 0, subtotal: 0, tax_amount: 0, total: 0 }
  );

  return (
    <ReportView
      title={t("sales.reports.tab.by_period")}
      filterArea={
        <DateRangeFilter
          dateFrom={dateFrom}
          setDateFrom={setDateFrom}
          dateTo={dateTo}
          setDateTo={setDateTo}
        />
      }
      onApply={() => setRanAt({ from: dateFrom, to: dateTo })}
      onReset={() => setRanAt(null)}
      onPrint={ranAt && rows.length > 0 ? () => window.print() : undefined}
      isLoading={reportQuery.isFetching}
      isError={reportQuery.isError}
      errorMessage={String(reportQuery.error ?? "")}
      onRetry={() => reportQuery.refetch()}
      isEmpty={!!ranAt && !reportQuery.isFetching && rows.length === 0}
      kpis={
        ranAt && rows.length > 0
          ? [
              { label: t("sales.reports.period.period"), value: String(rows.length) },
              { label: t("sales.reports.period.invoice_count"), value: String(totals.invoice_count) },
              { label: t("sales.reports.grand_total"), value: formatCurrency(totals.total) },
            ]
          : undefined
      }
    >
      {!ranAt && (
        <p className="text-sm text-muted-foreground">{t("sales.reports.run_hint")}</p>
      )}
      {ranAt && rows.length > 0 && (
        <>
          <ReportPrintHeader
            reportTitle={t("sales.reports.tab.by_period")}
            dateRangeLabel={`${ranAt.from} – ${ranAt.to}`}
          />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("sales.reports.period.period")}</TableHead>
                <TableHead className="text-end">{t("sales.reports.period.invoice_count")}</TableHead>
                <TableHead className="text-end">{t("sales.reports.period.subtotal")}</TableHead>
                <TableHead className="text-end">{t("sales.reports.period.tax")}</TableHead>
                <TableHead className="text-end font-semibold">{t("sales.reports.period.total")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.period_label}>
                  <TableCell className="font-medium tabular-nums">{row.period_label}</TableCell>
                  <TableCell className="text-end tabular-nums">{row.invoice_count}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.subtotal)}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(row.tax_amount)}</TableCell>
                  <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(row.total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell className="font-bold">{t("sales.reports.totals")}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{totals.invoice_count}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.subtotal)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.tax_amount)}</TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totals.total)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </>
      )}
    </ReportView>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SalesReportsPage() {
  const { t } = useI18n();

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("sales.reports.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("sales.reports.description")}</p>
      </div>

      <Tabs defaultValue="by_customer">
        <TabsList>
          <TabsTrigger value="by_customer">{t("sales.reports.tab.by_customer")}</TabsTrigger>
          <TabsTrigger value="by_product">{t("sales.reports.tab.by_product")}</TabsTrigger>
          <TabsTrigger value="by_period">{t("sales.reports.tab.by_period")}</TabsTrigger>
        </TabsList>

        <TabsContent value="by_customer" className="mt-4">
          <ByCustomerTab />
        </TabsContent>

        <TabsContent value="by_product" className="mt-4">
          <ByProductTab />
        </TabsContent>

        <TabsContent value="by_period" className="mt-4">
          <ByPeriodTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
