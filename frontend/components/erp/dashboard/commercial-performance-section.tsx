"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Banknote, FileText, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DashboardGrid } from "@/components/erp/dashboard/dashboard-grid";
import { KpiCard } from "@/components/erp/dashboard/kpi-card";
import { SalesTrendChart } from "@/components/erp/dashboard/sales-trend-chart";
import { RepresentativeBarChart } from "@/components/erp/dashboard/representative-bar-chart";
import { useI18n } from "@/lib/i18n/config";
import { formatCurrency } from "@/lib/format-currency";
import { reportingApi } from "@/features/reporting/api/client";
import { paymentsApi } from "@/features/payments/api/client";
import type { RepresentativePerformanceRow } from "@/features/reporting/api/types";

type Preset = "this_month" | "this_quarter" | "ytd";

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}
function iso(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function computePeriod(preset: Preset): {
  current: { from: string; to: string };
  previous: { from: string; to: string } | null;
} {
  const today = new Date();
  const y = today.getFullYear();
  const m = today.getMonth();
  if (preset === "this_month") {
    return {
      current: { from: iso(new Date(y, m, 1)), to: iso(today) },
      previous: { from: iso(new Date(y, m - 1, 1)), to: iso(new Date(y, m, 0)) },
    };
  }
  if (preset === "this_quarter") {
    const qStart = Math.floor(m / 3) * 3;
    return {
      current: { from: iso(new Date(y, qStart, 1)), to: iso(today) },
      previous: { from: iso(new Date(y, qStart - 3, 1)), to: iso(new Date(y, qStart, 0)) },
    };
  }
  // Year to Date: no prior-year comparison — not a supported convention
  // anywhere else in this codebase yet, so not invented here either.
  return { current: { from: iso(new Date(y, 0, 1)), to: iso(today) }, previous: null };
}

function sumBy(rows: RepresentativePerformanceRow[], pick: (r: RepresentativePerformanceRow) => string): number {
  return rows.reduce((acc, r) => acc + Number(pick(r)), 0);
}

function repChartPoints(rows: RepresentativePerformanceRow[], metric: "net_sales" | "collections" | "net_commission") {
  return rows.filter((r) => !r.is_unattributed).map((r) => ({ label: r.representative_name, value: Number(r[metric]) }));
}

function GrowthSubtext({ current, previous }: { current: number; previous: number | null }) {
  const { t } = useI18n();
  if (previous === null) return null;
  if (previous === 0) {
    return <span className="text-muted-foreground">{t("dashboard.commercial.growth_new")}</span>;
  }
  const pct = ((current - previous) / previous) * 100;
  const up = pct >= 0;
  return (
    <span className={up ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}>
      {up ? "↑" : "↓"} {Math.abs(pct).toFixed(0)}% {t("dashboard.commercial.vs_previous_period")}
    </span>
  );
}

/** Executive Dashboard redesign: a compact, self-contained Commercial
 * Performance section with its own period selector (This Month / This
 * Quarter / Year to Date), decoupled from the main dashboard's own
 * fiscal-year range. Every widget here reads from the exact same
 * `commercialByRepresentative` rollup (summed client-side for the KPI
 * cards, used as-is for the charts) — structurally the same source Sales
 * Reports and the Representative Performance page already use, so a card
 * can never disagree with its own chart or with the detailed reports. */
export function CommercialPerformanceSection({
  companyId,
  canView,
  canViewAr,
}: {
  companyId: string;
  canView: boolean;
  canViewAr: boolean;
}) {
  const { t } = useI18n();
  const [preset, setPreset] = useState<Preset>("this_month");
  const presetLabels: Record<Preset, string> = {
    this_month: t("dashboard.commercial.period.this_month"),
    this_quarter: t("dashboard.commercial.period.this_quarter"),
    ytd: t("dashboard.commercial.period.ytd"),
  };
  const { current, previous } = computePeriod(preset);
  const today = iso(new Date());

  const currentQuery = useQuery({
    queryKey: ["commercial-by-representative", companyId, current.from, current.to],
    queryFn: () => reportingApi.commercialByRepresentative(companyId, current.from, current.to),
    enabled: canView,
  });
  const previousQuery = useQuery({
    queryKey: ["commercial-by-representative", companyId, previous?.from, previous?.to],
    queryFn: () => reportingApi.commercialByRepresentative(companyId, previous!.from, previous!.to),
    enabled: canView && !!previous,
  });
  // Accounts Receivable: kept on the existing GL-based source
  // (JournalEntryRepository.account_balance_by_root_code via the
  // /dashboard endpoint) — not recomputed from the aging rows below, per
  // the approved "do not duplicate AR logic" rule. Requested with
  // period_start = period_end = today so it always reflects "as of now"
  // regardless of which preset is selected.
  const arQuery = useQuery({
    queryKey: ["dashboard-ar-balance", companyId, today],
    queryFn: () => reportingApi.getDashboard(companyId, today, today),
    enabled: canView,
  });
  // Overdue AR: reuses the existing AR Aging service unchanged — summed
  // over every bucket except "current" (days_overdue <= 0).
  const agingQuery = useQuery({
    queryKey: ["ar-aging-for-dashboard", companyId, today],
    queryFn: () => paymentsApi.arAging(companyId, today),
    enabled: canView && canViewAr,
  });
  const trendQuery = useQuery({
    queryKey: ["commercial-net-sales-trend", companyId, current.from, current.to],
    queryFn: () => reportingApi.commercialNetSalesTrend(companyId, current.from, current.to),
    enabled: canView,
  });

  if (!canView) return null;

  const rows = currentQuery.data ?? [];
  const prevRows = previousQuery.data ?? [];
  const isLoading = currentQuery.isLoading || arQuery.isLoading || trendQuery.isLoading;

  const netSales = sumBy(rows, (r) => r.net_sales);
  const prevNetSales = previous ? sumBy(prevRows, (r) => r.net_sales) : null;
  const collections = sumBy(rows, (r) => r.collections);
  const prevCollections = previous ? sumBy(prevRows, (r) => r.collections) : null;

  const ar = arQuery.data ? Number(arQuery.data.receivables_balance) : 0;
  const overdueAr = (agingQuery.data?.rows ?? [])
    .filter((r) => r.bucket !== "current")
    .reduce((acc, r) => acc + Number(r.balance_due), 0);

  const alerts: string[] = [];
  if (previous && prevNetSales !== null && prevNetSales > 0 && netSales < prevNetSales) {
    alerts.push(t("dashboard.commercial.alerts.declining"));
  }
  if (netSales > 0 && collections < netSales * 0.5) {
    alerts.push(t("dashboard.commercial.alerts.low_collections"));
  }
  if (canViewAr && ar > 0 && overdueAr > ar * 0.3) {
    alerts.push(t("dashboard.commercial.alerts.high_overdue"));
  }
  const shownAlerts = alerts.slice(0, 3);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("dashboard.commercial.title")}</h2>
        <Select value={preset} onValueChange={(v) => v && setPreset(v as Preset)}>
          <SelectTrigger className="h-8 w-44 text-sm">
            <SelectValue>{(value: string) => presetLabels[value as Preset] ?? value}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="this_month">{t("dashboard.commercial.period.this_month")}</SelectItem>
            <SelectItem value="this_quarter">{t("dashboard.commercial.period.this_quarter")}</SelectItem>
            <SelectItem value="ytd">{t("dashboard.commercial.period.ytd")}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Row 1 — exactly 4 primary KPI cards, one authoritative figure each */}
      <DashboardGrid>
        <KpiCard
          label={t("dashboard.commercial.net_sales")}
          value={formatCurrency(netSales)}
          isLoading={isLoading}
          icon={TrendingUp}
          accentClassName="bg-[#2a78d6]/15 text-[#2a78d6] dark:bg-[#3987e5]/20 dark:text-[#3987e5]"
          subtext={<GrowthSubtext current={netSales} previous={prevNetSales} />}
        />
        <KpiCard
          label={t("dashboard.commercial.total_collections")}
          value={formatCurrency(collections)}
          isLoading={isLoading}
          icon={Banknote}
          accentClassName="bg-[#e87ba4]/15 text-[#e87ba4] dark:bg-[#d55181]/20 dark:text-[#d55181]"
          subtext={<GrowthSubtext current={collections} previous={prevCollections} />}
        />
        <KpiCard
          label={t("dashboard.commercial.accounts_receivable")}
          value={formatCurrency(ar)}
          isLoading={isLoading}
          icon={FileText}
          accentClassName="bg-[#1baf7a]/15 text-[#1baf7a] dark:bg-[#199e70]/20 dark:text-[#199e70]"
        />
        <KpiCard
          label={t("dashboard.commercial.overdue_ar")}
          value={canViewAr ? formatCurrency(overdueAr) : "—"}
          isLoading={isLoading && canViewAr}
          icon={AlertTriangle}
          accentClassName="bg-[#eda100]/15 text-[#eda100] dark:bg-[#c98500]/20 dark:text-[#c98500]"
        />
      </DashboardGrid>

      {/* Row 2 — visual comparison only, no detailed table beneath */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.commercial.sales_by_rep_chart.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-32 animate-pulse rounded-md bg-muted" />
            ) : (
              <RepresentativeBarChart points={repChartPoints(rows, "net_sales")} colorClassName="bg-[#2a78d6] dark:bg-[#3987e5]" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.commercial.collections_by_rep_chart.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-32 animate-pulse rounded-md bg-muted" />
            ) : (
              <RepresentativeBarChart points={repChartPoints(rows, "collections")} colorClassName="bg-[#e87ba4] dark:bg-[#d55181]" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.commercial.net_commission_by_rep_chart.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-32 animate-pulse rounded-md bg-muted" />
            ) : (
              <RepresentativeBarChart
                points={repChartPoints(rows, "net_commission")}
                colorClassName="bg-[#eda100] dark:bg-[#c98500]"
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Row 3 — one trend, one compact alerts panel */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.commercial.net_sales_trend.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-40 animate-pulse rounded-md bg-muted" />
            ) : trendQuery.data && trendQuery.data.length > 0 ? (
              <SalesTrendChart points={trendQuery.data.map((p) => ({ period_label: p.period_label, total: p.net_sales }))} />
            ) : (
              <p className="py-12 text-center text-sm text-muted-foreground">{t("common.empty")}</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.commercial.alerts.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-16 animate-pulse rounded-md bg-muted" />
            ) : shownAlerts.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("dashboard.commercial.alerts.none")}</p>
            ) : (
              <ul className="space-y-2">
                {shownAlerts.map((text) => (
                  <li key={text} className="flex items-start gap-2 text-sm">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                    <span>{text}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
