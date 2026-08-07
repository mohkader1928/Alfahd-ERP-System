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
import { salesApi } from "@/features/sales/api/client";
import type { SalesInvoice } from "@/features/sales/api/types";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { statusVariant } from "@/lib/status-variant";

const INVOICE_STATUSES = ["draft", "pending_submission", "cleared", "reported", "rejected", "cancelled"];

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

export default function SalesInvoicesPage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const customer = useCustomerLabel();
  const [filters, setFilters] = useState<Record<string, string>>({});

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["sales-invoices", companyId, filters.status, filters.date_from, filters.date_to],
    queryFn: () =>
      salesApi.listInvoices(companyId, {
        status: filters.status || undefined,
        dateFrom: filters.date_from || undefined,
        dateTo: filters.date_to || undefined,
        pageSize: 200,
      }),
  });
  const invoices = data?.items;

  const filterFields: FilterFieldConfig[] = [
    {
      key: "status",
      label: t("sales.quotations.status"),
      type: "select",
      options: INVOICE_STATUSES.map((s) => ({ value: s, label: s })),
      width: "w-44",
    },
    { key: "date_from", label: t("sales.reports.date_from"), type: "date" },
    { key: "date_to", label: t("sales.reports.date_to"), type: "date" },
  ];

  const columns: ERPColumn<SalesInvoice>[] = [
    {
      key: "number",
      header: t("sales.quotations.number"),
      sortable: true,
      sortValue: (row) => row.number,
      render: (row) => (
        <Link href={`/sales/invoices/${row.id}`} className="font-medium underline-offset-4 hover:underline">
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
      key: "invoice_type",
      header: t("sales.invoice.type"),
      render: (row) => <span className="capitalize">{row.invoice_type.replace("_", " ")}</span>,
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
      title={t("sales.invoices.title")}
      breadcrumbs={[{ label: t("nav.sales") }, { label: t("sales.invoices.title") }]}
      columns={columns}
      rows={invoices}
      rowKey={(row) => row.id}
      getRowHref={(row) => `/sales/invoices/${row.id}`}
      isLoading={isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["sales-invoices", companyId] })}
      searchPlaceholder={t("list.search_placeholder")}
      searchText={(row) => `${row.number} ${customer.label(row.partner_id)}`}
      emptyDescription={t("sales.invoices.empty_description")}
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
