"use client";

import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { salesApi } from "@/features/sales/api/client";
import type { Quotation } from "@/features/sales/api/types";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";

/** Same local-resolver convention Purchasing/Inventory/Sales Orders/
 * Invoices already use — never show a raw partner UUID when a name is
 * available. */
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

/**
 * Phase 17A reference implementation: this page is the proof that
 * ERPListView (Part 2) covers a real screen's needs — search, sort,
 * pagination, permission-gated Create, refresh, and all UI states — without
 * any change to what data is fetched or how a quotation is created. Other
 * list pages (Accounting/Inventory/Purchasing tabs, admin) are migrated
 * incrementally in later phases, not in this pass.
 */
export default function QuotationsPage() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const customer = useCustomerLabel();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["quotations", companyId],
    queryFn: () => salesApi.listQuotations(companyId),
  });

  const columns: ERPColumn<Quotation>[] = [
    {
      key: "number",
      header: t("sales.quotations.number"),
      sortable: true,
      sortValue: (row) => row.number,
      render: (row) => (
        <Link href={`/sales/quotations/${row.id}`} className="font-medium underline-offset-4 hover:underline">
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
      key: "quote_date",
      header: t("sales.quotations.date"),
      sortable: true,
      sortValue: (row) => row.quote_date,
      render: (row) => formatDate(row.quote_date, locale),
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
      title={t("sales.quotations.title")}
      breadcrumbs={[{ label: t("nav.sales") }, { label: t("sales.quotations.title") }]}
      columns={columns}
      rows={data}
      rowKey={(row) => row.id}
      getRowHref={(row) => `/sales/quotations/${row.id}`}
      isLoading={isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["quotations", companyId] })}
      searchPlaceholder={t("list.search_placeholder")}
      searchText={(row) => `${row.number} ${customer.label(row.partner_id)}`}
      createAction={{ label: t("sales.quotations.new"), href: "/sales/quotations/new", permission: "sales.quotation.create" }}
    />
  );
}
