"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, FileText, ShoppingCart, Wallet } from "lucide-react";
import { DashboardGrid } from "@/components/erp/dashboard/dashboard-grid";
import { KpiCard } from "@/components/erp/dashboard/kpi-card";
import { SalesTrendChart } from "@/components/erp/dashboard/sales-trend-chart";
import { RecentActivityFeed } from "@/components/erp/dashboard/recent-activity-feed";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { useCompanyName } from "@/hooks/use-company-name";
import { formatCurrency } from "@/lib/format-currency";
import { reportingApi } from "@/features/reporting/api/client";

function currentYearRange() {
  const year = new Date().getFullYear();
  return { start: `${year}-01-01`, end: `${year}-12-31` };
}

export default function DashboardPage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { start, end } = currentYearRange();
  const { name: companyName, company, isLoading: companyLoading } = useCompanyName();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard", companyId, start, end],
    queryFn: () => reportingApi.getDashboard(companyId, start, end),
  });

  const cards = [
    { key: "dashboard.period_sales", value: data?.period_sales_total },
    { key: "dashboard.period_purchases", value: data?.period_purchases_total },
    { key: "dashboard.receivables", value: data?.receivables_balance, href: "/accounting?tab=ar-aging" },
    { key: "dashboard.payables", value: data?.payables_balance, href: "/accounting?tab=ap-aging" },
  ];

  const pendingApprovals = data?.pending_approvals_count ?? 0;

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
          />
        ))}
      </DashboardGrid>

      {!isLoading && pendingApprovals > 0 && (
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.sales_trend.title")}</CardTitle>
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
            <CardTitle className="text-base">{t("dashboard.quick_actions.title")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <Link href="/sales/quotations">
              <Button variant="outline" className="w-full justify-start gap-2">
                <FileText className="h-4 w-4" />
                {t("dashboard.quick_actions.new_quotation")}
              </Button>
            </Link>
            <Link href="/purchasing/orders/new">
              <Button variant="outline" className="w-full justify-start gap-2">
                <ShoppingCart className="h-4 w-4" />
                {t("dashboard.quick_actions.new_purchase_order")}
              </Button>
            </Link>
            <Link href="/payments">
              <Button variant="outline" className="w-full justify-start gap-2">
                <Wallet className="h-4 w-4" />
                {t("dashboard.quick_actions.record_payment")}
              </Button>
            </Link>
          </CardContent>
        </Card>
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
