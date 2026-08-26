"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, FileText, Landmark, ShoppingCart, TrendingUp, Wallet } from "lucide-react";
import { DashboardGrid } from "@/components/erp/dashboard/dashboard-grid";
import { KpiCard } from "@/components/erp/dashboard/kpi-card";
import { SalesTrendChart } from "@/components/erp/dashboard/sales-trend-chart";
import { QuarterlySalesChart } from "@/components/erp/dashboard/quarterly-sales-chart";
import { RecentActivityFeed } from "@/components/erp/dashboard/recent-activity-feed";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { PermissionDenied } from "@/components/erp/states/permission-denied";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { useCompanyName } from "@/hooks/use-company-name";
import { useMyPermissions } from "@/hooks/use-permissions";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { reportingApi } from "@/features/reporting/api/client";

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

/** P0-8: the fiscal year (not necessarily calendar-aligned) containing
 * today, computed from the company's configured fiscal_year_start_month
 * (1 = January, the default — identical to the old hardcoded Jan-Dec
 * range for every company that hasn't changed it). Drives both the KPI
 * cards and the trend chart below, so they always describe the same
 * period instead of two unrelated ones. */
function currentFiscalYearRange(fiscalYearStartMonth: number) {
  const today = new Date();
  const startYear = today.getMonth() + 1 >= fiscalYearStartMonth ? today.getFullYear() : today.getFullYear() - 1;
  const start = new Date(startYear, fiscalYearStartMonth - 1, 1);
  const end = new Date(startYear + 1, fiscalYearStartMonth - 1, 0); // day 0 = last day of prior month
  return {
    start: `${start.getFullYear()}-${pad2(start.getMonth() + 1)}-${pad2(start.getDate())}`,
    end: `${end.getFullYear()}-${pad2(end.getMonth() + 1)}-${pad2(end.getDate())}`,
  };
}

export default function DashboardPage() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { name: companyName, company, isLoading: companyLoading } = useCompanyName();
  const { start, end } = currentFiscalYearRange(company?.fiscal_year_start_month ?? 1);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["dashboard", companyId, start, end],
    queryFn: () => reportingApi.getDashboard(companyId, start, end),
    enabled: !companyLoading,
  });
  const { can } = useMyPermissions();

  if (isError && error instanceof ApiError && error.status === 403) {
    return <PermissionDenied />;
  }

  // Hardening Sub-stage 1 redesign: each KPI gets a fixed categorical
  // accent (dataviz skill slots 1-5, colorblind-safe) so the five cards
  // are scannable at a glance instead of five identical gray rectangles —
  // never cycled/random, the same KPI always reads the same color+icon.
  // Each also carries the permission code for the module its own figure
  // (or its href's destination) belongs to -- a role scoped to one module
  // sees only that module's tiles, instead of a tile whose value it can't
  // see or whose click 403s.
  const allCards = [
    {
      key: "dashboard.period_sales",
      value: data?.period_sales_total,
      icon: TrendingUp,
      permission: "reporting.sales.view",
      accent: "bg-[#2a78d6]/15 text-[#2a78d6] dark:bg-[#3987e5]/20 dark:text-[#3987e5]",
    },
    {
      key: "dashboard.period_purchases",
      value: data?.period_purchases_total,
      icon: ShoppingCart,
      permission: "reporting.purchasing.view",
      accent: "bg-[#eb6834]/15 text-[#eb6834] dark:bg-[#d95926]/20 dark:text-[#d95926]",
    },
    {
      key: "dashboard.receivables",
      value: data?.receivables_balance,
      href: "/accounting?tab=ar-aging",
      icon: FileText,
      permission: "payment.aging.view",
      accent: "bg-[#1baf7a]/15 text-[#1baf7a] dark:bg-[#199e70]/20 dark:text-[#199e70]",
    },
    {
      key: "dashboard.payables",
      value: data?.payables_balance,
      href: "/accounting?tab=ap-aging",
      icon: Landmark,
      permission: "payment.aging.view",
      accent: "bg-[#eda100]/15 text-[#eda100] dark:bg-[#c98500]/20 dark:text-[#c98500]",
    },
    {
      key: "dashboard.cash_balance",
      value: data?.cash_balance,
      href: "/accounting?tab=trial-balance",
      icon: Wallet,
      permission: "accounting.reports.trial_balance.view",
      accent: "bg-[#e87ba4]/15 text-[#e87ba4] dark:bg-[#d55181]/20 dark:text-[#d55181]",
    },
  ];
  const cards = allCards.filter((card) => can(card.permission));

  const pendingApprovals = data?.pending_approvals_count ?? 0;
  const canViewPurchasing = can("purchasing.order.view");

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <EntityImage src={company?.logo_path} name={companyName ?? ""} shape="square" size="md" isLoading={companyLoading} />
        <div>
          <h1 className="text-2xl font-semibold">{t("dashboard.title")}</h1>
          {companyName && <p className="text-sm text-muted-foreground">{companyName}</p>}
        </div>
      </div>

      <DashboardGrid>
        {cards.map((card) => (
          <KpiCard
            key={card.key}
            label={t(card.key)}
            value={formatCurrency(card.value ?? "0")}
            isLoading={isLoading}
            isError={isError}
            href={card.href}
            icon={card.icon}
            accentClassName={card.accent}
          />
        ))}
      </DashboardGrid>

      {!isLoading && pendingApprovals > 0 && canViewPurchasing && (
        <Link href="/purchasing">
          <Card className="border-amber-300 bg-amber-50 transition-colors hover:bg-amber-100 dark:border-amber-900 dark:bg-amber-950/30 dark:hover:bg-amber-950/50">
            <CardContent className="flex items-center gap-3 py-4">
              <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
              <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
                {pendingApprovals === 1
                  ? t("dashboard.pending_approvals.one")
                  : `${pendingApprovals} ${t("dashboard.pending_approvals.many")}`}
              </p>
            </CardContent>
          </Card>
        </Link>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.sales_trend.title")}</CardTitle>
            <p className="text-xs text-muted-foreground">
              {formatDate(start, locale)} – {formatDate(end, locale)}
            </p>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-40 animate-pulse rounded-md bg-muted" />
            ) : data && data.sales_trend.length > 0 ? (
              <SalesTrendChart points={data.sales_trend} />
            ) : (
              <p className="py-12 text-center text-sm text-muted-foreground">{t("common.empty")}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.quarterly_sales.title")}</CardTitle>
            <p className="text-xs text-muted-foreground">
              {formatDate(start, locale)} – {formatDate(end, locale)}
            </p>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-40 animate-pulse rounded-md bg-muted" />
            ) : data ? (
              <QuarterlySalesChart points={data.sales_trend} />
            ) : (
              <p className="py-12 text-center text-sm text-muted-foreground">{t("common.empty")}</p>
            )}
          </CardContent>
        </Card>

        {(can("sales.quotation.create") || can("purchasing.order.create") || can("payment.create")) && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("dashboard.quick_actions.title")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {can("sales.quotation.create") && (
                <Link href="/sales/quotations">
                  <Button variant="outline" className="w-full justify-start gap-2">
                    <FileText className="h-4 w-4" />
                    {t("dashboard.quick_actions.new_quotation")}
                  </Button>
                </Link>
              )}
              {can("purchasing.order.create") && (
                <Link href="/purchasing/orders/new">
                  <Button variant="outline" className="w-full justify-start gap-2">
                    <ShoppingCart className="h-4 w-4" />
                    {t("dashboard.quick_actions.new_purchase_order")}
                  </Button>
                </Link>
              )}
              {can("payment.create") && (
                <Link href="/payments">
                  <Button variant="outline" className="w-full justify-start gap-2">
                    <Wallet className="h-4 w-4" />
                    {t("dashboard.quick_actions.record_payment")}
                  </Button>
                </Link>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("dashboard.recent_activity.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-12 animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          ) : (
            <RecentActivityFeed items={data?.recent_activity ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
