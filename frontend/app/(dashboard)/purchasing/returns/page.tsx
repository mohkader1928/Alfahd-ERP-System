"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { FilterBar, type FilterFieldConfig } from "@/components/erp/filter-bar/filter-bar";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import type { VendorBill } from "@/features/purchasing/api/types";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";

const RETURN_STATUSES = ["matched", "mismatched", "posted"];

function useVendorLabel() {
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const vendorsQuery = useQuery({
    queryKey: ["partners", companyId, "vendor"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });
  return {
    label: (partnerId: string) => vendorsQuery.data?.find((p) => p.id === partnerId)?.name ?? partnerId,
  };
}

/**
 * P0-9 follow-up (Owner feedback): mirrors the Sales Returns screen —
 * "مرتجع مشتريات" as its own discoverable item in the Purchasing menu,
 * distinct from the Debit Note action buried in a bill's detail page.
 * A Purchase Return already is a debit note (bill_type=debit_note) in
 * the data model; this is a dedicated list + creation flow for it.
 */
export default function PurchaseReturnsPage() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const vendor = useVendorLabel();
  const [filters, setFilters] = useState<Record<string, string>>({});

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["purchase-returns", companyId, filters.status, filters.date_from, filters.date_to],
    queryFn: () =>
      purchasingApi.listVendorBills(companyId, {
        billType: "debit_note",
        status: filters.status || undefined,
        dateFrom: filters.date_from || undefined,
        dateTo: filters.date_to || undefined,
        pageSize: 200,
      }),
  });
  const returns = data?.items;

  const filterFields: FilterFieldConfig[] = [
    {
      key: "status",
      label: t("purchasing.orders.status"),
      type: "select",
      options: RETURN_STATUSES.map((s) => ({ value: s, label: s })),
      width: "w-44",
    },
    { key: "date_from", label: t("sales.reports.date_from"), type: "date" },
    { key: "date_to", label: t("sales.reports.date_to"), type: "date" },
  ];

  const columns: ERPColumn<VendorBill>[] = [
    {
      key: "number",
      header: t("purchasing.orders.number"),
      sortable: true,
      sortValue: (row) => row.number,
      render: (row) => (
        <Link href={`/purchasing/bills/${row.id}`} className="font-medium underline-offset-4 hover:underline">
          {row.number}
        </Link>
      ),
    },
    {
      key: "partner_id",
      header: t("purchasing.orders.vendor"),
      render: (row) => vendor.label(row.partner_id),
    },
    {
      key: "original_bill_id",
      header: t("purchasing.returns.original_bill"),
      render: (row) =>
        row.original_bill_id ? (
          <Link href={`/purchasing/bills/${row.original_bill_id}`} className="underline-offset-4 hover:underline">
            {t("common.view")}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      key: "bill_date",
      header: t("purchasing.orders.date"),
      sortable: true,
      sortValue: (row) => row.bill_date,
      render: (row) => formatDate(row.bill_date, locale),
    },
    {
      key: "status",
      header: t("purchasing.orders.status"),
      sortable: true,
      sortValue: (row) => row.status,
      render: (row) => <Badge variant={statusVariant(row.status)}>{row.status}</Badge>,
    },
    {
      key: "total_amount",
      header: t("purchasing.orders.total"),
      align: "end",
      sortable: true,
      sortValue: (row) => Number(row.total_amount),
      render: (row) => formatCurrency(row.total_amount),
    },
  ];

  return (
    <ERPListView
      title={t("nav.purchasing.returns")}
      breadcrumbs={[{ label: t("nav.purchasing") }, { label: t("nav.purchasing.returns") }]}
      columns={columns}
      rows={returns}
      rowKey={(row) => row.id}
      getRowHref={(row) => `/purchasing/bills/${row.id}`}
      isLoading={isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["purchase-returns", companyId] })}
      searchPlaceholder={t("list.search_placeholder")}
      searchText={(row) => `${row.number} ${vendor.label(row.partner_id)}`}
      emptyDescription={t("purchasing.returns.empty_description")}
      createAction={{
        label: t("purchasing.returns.new"),
        href: "/purchasing/returns/new",
        permission: "purchasing.vendor_bill.debit_note",
      }}
      filters={
        <FilterBar
          fields={filterFields}
          values={filters}
          onChange={(key, value) => setFilters((prev) => ({ ...prev, [key]: value }))}
          onClear={() => setFilters({})}
        />
      }
    />
  );
}
