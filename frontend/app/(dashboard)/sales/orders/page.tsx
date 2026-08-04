"use client";

import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { salesApi } from "@/features/sales/api/client";
import type { SalesOrder } from "@/features/sales/api/types";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";

/** Same local-resolver convention Purchasing/Inventory already use for
 * vendor/product names — kept per-page rather than introducing a new
 * shared hook for a single new consumer. */
function useCustomerLabel() {
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const customersQuery = useQuery({
    queryKey: ["partners", companyId, "customer"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { customersOnly: true }),
  });
  return {
    label: (partnerId: string) => customersQuery.data?.find((p) => p.id === partnerId)?.name ?? partnerId,
  };
}

export default function SalesOrdersPage() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const customer = useCustomerLabel();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["sales-orders", companyId],
    queryFn: () => salesApi.listOrders(companyId),
  });

  const columns: ERPColumn<SalesOrder>[] = [
    {
      key: "number",
      header: t("sales.quotations.number"),
      sortable: true,
      sortValue: (row) => row.number,
      render: (row) => (
        <Link href={`/sales/orders/${row.id}`} className="font-medium underline-offset-4 hover:underline">
          {row.number}
        </Link>
      ),
    },
    {
      key: "partner_id",
      header: t("sales.orders.customer"),
      render: (row) => customer.label(row.partner_id),
    },
    {
      key: "order_date",
      header: t("sales.quotations.date"),
      sortable: true,
      sortValue: (row) => row.order_date,
      render: (row) => formatDate(row.order_date, locale),
    },
    {
      key: "status",
      header: t("sales.quotations.status"),
      sortable: true,
      sortValue: (row) => row.status,
      render: (row) => <Badge variant={statusVariant(row.status)}>{row.status}</Badge>,
    },
    {
      key: "total_amount",
      header: t("sales.quotations.total"),
      align: "end",
      sortable: true,
      sortValue: (row) => Number(row.total_amount),
      render: (row) => formatCurrency(row.total_amount),
    },
  ];

  return (
    <ERPListView
      title={t("sales.orders.title")}
      breadcrumbs={[{ label: t("nav.sales") }, { label: t("sales.orders.title") }]}
      columns={columns}
      rows={data}
      rowKey={(row) => row.id}
      getRowHref={(row) => `/sales/orders/${row.id}`}
      isLoading={isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["sales-orders", companyId] })}
      searchPlaceholder={t("list.search_placeholder")}
      searchText={(row) => `${row.number} ${customer.label(row.partner_id)}`}
      emptyDescription={t("sales.orders.empty_description")}
    />
  );
}
