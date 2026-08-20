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
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";

const RETURN_STATUSES = ["draft", "pending_submission", "cleared", "reported", "rejected", "cancelled"];

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
 * P0-9 follow-up (Owner feedback): the restock option added to the
 * Invoice detail page's credit-note form was too buried — the Owner
 * asked for "مرتجع مبيعات" as its own discoverable item in the Sales
 * menu, distinct from the Credit Note action. This is that screen: a
 * dedicated list of every credit note (invoice_type=credit_note, which
 * is exactly what a Sales Return already is in the data model — no new
 * document type needed), with its own "New Return" entry point.
 */
export default function SalesReturnsPage() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const customer = useCustomerLabel();
  const [filters, setFilters] = useState<Record<string, string>>({});

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["sales-returns", companyId, filters.status, filters.date_from, filters.date_to],
    queryFn: () =>
      salesApi.listInvoices(companyId, {
        invoiceType: "credit_note",
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
      label: t("sales.quotations.status"),
      type: "select",
      options: RETURN_STATUSES.map((s) => ({ value: s, label: s })),
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
      sortable: true,
      sortValue: (row) => customer.label(row.partner_id),
      render: (row) => customer.label(row.partner_id),
    },
    {
      key: "original_invoice_id",
      header: t("sales.returns.original_invoice"),
      sortable: true,
      sortValue: (row) => row.original_invoice_id ?? "",
      render: (row) =>
        row.original_invoice_id ? (
          <Link
            href={`/sales/invoices/${row.original_invoice_id}`}
            className="underline-offset-4 hover:underline"
          >
            {t("common.view")}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      key: "invoice_date",
      header: t("sales.invoice.date"),
      sortable: true,
      sortValue: (row) => row.invoice_date,
      render: (row) => formatDate(row.invoice_date, locale),
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
      title={t("nav.sales.returns")}
      breadcrumbs={[{ label: t("nav.sales") }, { label: t("nav.sales.returns") }]}
      columns={columns}
      rows={returns}
      rowKey={(row) => row.id}
      getRowHref={(row) => `/sales/invoices/${row.id}`}
      isLoading={isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["sales-returns", companyId] })}
      searchPlaceholder={t("list.search_placeholder")}
      searchText={(row) => `${row.number} ${customer.label(row.partner_id)}`}
      emptyDescription={t("sales.returns.empty_description")}
      createAction={{ label: t("sales.returns.new"), href: "/sales/returns/new", permission: "sales.invoice.credit_note" }}
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
