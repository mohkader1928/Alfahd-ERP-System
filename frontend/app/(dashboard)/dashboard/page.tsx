"use client";

import { useQuery } from "@tanstack/react-query";
import { DashboardGrid } from "@/components/erp/dashboard/dashboard-grid";
import { KpiCard } from "@/components/erp/dashboard/kpi-card";
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
      <DashboardGrid>
        {cards.map((card) => (
          <KpiCard
            key={card.key}
            label={t(card.key)}
            value={formatSar(card.value ?? "0")}
            isLoading={isLoading}
            isError={isError}
          />
        ))}
      </DashboardGrid>
    </div>
  );
}
