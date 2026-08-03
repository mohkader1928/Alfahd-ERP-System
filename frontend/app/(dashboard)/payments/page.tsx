"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { paymentsApi } from "@/features/payments/api/client";
import type { Payment } from "@/features/payments/api/types";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";

export default function PaymentsPage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["payments", companyId],
    queryFn: () => paymentsApi.listPayments(companyId),
  });

  const columns: ERPColumn<Payment>[] = [
    {
      key: "number",
      header: t("payments.number"),
      sortable: true,
      sortValue: (row) => row.number,
      render: (row) => <span className="font-medium">{row.number}</span>,
    },
    {
      key: "payment_type",
      header: t("payments.type"),
      sortable: true,
      sortValue: (row) => row.payment_type,
      render: (row) => (
        <Badge variant={row.payment_type === "customer" ? "default" : "secondary"}>
          {row.payment_type === "customer" ? t("payments.type.customer") : t("payments.type.vendor")}
        </Badge>
      ),
    },
    {
      key: "payment_date",
      header: t("payments.date"),
      sortable: true,
      sortValue: (row) => row.payment_date,
      render: (row) => row.payment_date,
    },
    {
      key: "amount",
      header: t("payments.amount"),
      align: "end",
      sortable: true,
      sortValue: (row) => Number(row.amount),
      render: (row) => formatCurrency(row.amount, row.currency_code),
    },
    {
      key: "reference",
      header: t("payments.reference"),
      render: (row) => row.reference ?? "—",
    },
  ];

  return (
    <ERPListView
      title={t("payments.title")}
      breadcrumbs={[{ label: t("payments.title") }]}
      columns={columns}
      rows={data}
      rowKey={(row) => row.id}
      isLoading={isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["payments", companyId] })}
      searchPlaceholder={t("list.search_placeholder")}
      searchText={(row) => `${row.number} ${row.reference ?? ""}`}
      createAction={{ label: t("payments.new"), href: "/payments/new", permission: "payment.create" }}
    />
  );
}
