"use client";

import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { paymentsApi } from "@/features/payments/api/client";
import type { Payment, PaymentType } from "@/features/payments/api/types";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";

// Owner directive: customer receipts and vendor payments must live as
// separate screens in their own module (Sales / Purchasing), not one
// shared list with a Type column the user has to scan. Shared here so
// the /sales/receipts and /purchasing/payments screens (and /payments,
// the original type-agnostic view, kept for back-compat) don't each
// reimplement the same query/columns/list wiring.
export function PaymentListView({
  paymentType,
  title,
  newHref,
  newLabel,
}: {
  /** Omit to show both types together (the original, still-generic
   * /payments view) — a Type column appears only in that case, since a
   * type-scoped screen makes it redundant. */
  paymentType?: PaymentType;
  title: string;
  newHref: string;
  newLabel: string;
}) {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["payments", companyId, paymentType],
    queryFn: () => paymentsApi.listPayments(companyId, paymentType),
  });

  const columns: ERPColumn<Payment>[] = [
    {
      key: "number",
      header: t("payments.number"),
      sortable: true,
      sortValue: (row) => row.number,
      render: (row) => (
        <Link href={`/payments/${row.id}`} className="font-medium underline-offset-4 hover:underline">
          {row.number}
        </Link>
      ),
    },
    ...(paymentType
      ? []
      : [
          {
            key: "payment_type",
            header: t("payments.type"),
            sortable: true,
            sortValue: (row: Payment) => row.payment_type,
            render: (row: Payment) => (
              <Badge variant={row.payment_type === "customer" ? "default" : "secondary"}>
                {row.payment_type === "customer" ? t("payments.type.customer") : t("payments.type.vendor")}
              </Badge>
            ),
          } satisfies ERPColumn<Payment>,
        ]),
    {
      key: "payment_date",
      header: t("payments.date"),
      sortable: true,
      sortValue: (row) => row.payment_date,
      render: (row) => formatDate(row.payment_date, locale),
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
      title={title}
      breadcrumbs={[{ label: title }]}
      columns={columns}
      rows={data}
      rowKey={(row) => row.id}
      getRowHref={(row) => `/payments/${row.id}`}
      isLoading={isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["payments", companyId, paymentType] })}
      searchPlaceholder={t("list.search_placeholder")}
      searchText={(row) => `${row.number} ${row.reference ?? ""}`}
      createAction={{ label: newLabel, href: newHref, permission: "payment.create" }}
    />
  );
}
