"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { reportingApi } from "@/features/reporting/api/client";

function currentYearRange() {
  const year = new Date().getFullYear();
  return { start: `${year}-01-01`, end: `${year}-12-31` };
}

function formatSar(value: string) {
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} SAR`;
}

export default function DashboardPage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { start, end } = currentYearRange();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard", companyId, start, end],
    queryFn: () => reportingApi.getDashboard(companyId, start, end),
  });

  const cards = [
    { key: "dashboard.period_sales", value: data?.period_sales_total },
    { key: "dashboard.period_purchases", value: data?.period_purchases_total },
    { key: "dashboard.receivables", value: data?.receivables_balance },
    { key: "dashboard.payables", value: data?.payables_balance },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t("dashboard.title")}</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.key}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{t(card.key)}</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <Skeleton className="h-8 w-32" />
              ) : isError ? (
                <p className="text-sm text-destructive">{t("common.error")}</p>
              ) : (
                <p className="text-2xl font-semibold">{formatSar(card.value ?? "0")}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
