"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { FilterBar, type FilterFieldConfig } from "@/components/erp/filter-bar/filter-bar";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";
import type { PurchaseOrder, VendorBill } from "@/features/purchasing/api/types";

const PO_STATUSES = ["draft", "pending_approval", "confirmed", "partially_received", "done", "closed", "cancelled"];
const BILL_STATUSES = ["draft", "matched", "mismatched", "approved", "posted"];

/**
 * Bundle 3 — Purchasing/Inventory List Consistency. Both tabs now sit on
 * the same `ERPListView` every other list screen in the app uses (search,
 * sort, pagination, permission-gated actions, shared empty/error states)
 * instead of a hand-rolled <Table> — closing the "two different UI
 * qualities in the same app" finding from docs/18-ui-ux-audit.md (A1/A5/A6).
 * No business logic changed: same endpoints, same fields, same workflow.
 */
function useVendorLabel() {
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const vendorsQuery = useQuery({
    queryKey: ["partners", companyId, "vendor"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });
  return {
    isLoading: vendorsQuery.isLoading,
    label: (partnerId: string) => vendorsQuery.data?.find((p) => p.id === partnerId)?.name ?? partnerId,
  };
}

function OrdersTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const { label: vendorLabel } = useVendorLabel();
  const [filters, setFilters] = useState<Record<string, string>>({});

  const ordersQuery = useQuery({
    queryKey: ["purchase-orders", companyId, filters.status, filters.date_from, filters.date_to],
    queryFn: () =>
      purchasingApi.listOrders(companyId, {
        status: filters.status || undefined,
        dateFrom: filters.date_from || undefined,
        dateTo: filters.date_to || undefined,
        pageSize: 200,
      }),
  });
  const orders = ordersQuery.data?.items;

  const filterFields: FilterFieldConfig[] = [
    {
      key: "status",
      label: t("purchasing.orders.status"),
      type: "select",
      options: PO_STATUSES.map((s) => ({ value: s, label: t(`purchasing.orders.status_${s}`) })),
      width: "w-44",
    },
    { key: "date_from", label: t("sales.reports.date_from"), type: "date" },
    { key: "date_to", label: t("sales.reports.date_to"), type: "date" },
  ];

  const columns: ERPColumn<PurchaseOrder>[] = [
    {
      key: "number",
      header: t("purchasing.orders.number"),
      sortable: true,
      sortValue: (r) => r.number,
      render: (r) => (
        <Link href={`/purchasing/orders/${r.id}`} className="font-medium underline-offset-4 hover:underline">
          {r.number}
        </Link>
      ),
    },
    { key: "vendor", header: t("purchasing.orders.vendor"), render: (r) => vendorLabel(r.partner_id) },
    { key: "order_date", header: t("purchasing.orders.date"), sortable: true, sortValue: (r) => r.order_date, render: (r) => formatDate(r.order_date, locale) },
    {
      key: "status",
      header: t("purchasing.orders.status"),
      render: (r) => <Badge variant={statusVariant(r.status)}>{t(`purchasing.orders.status_${r.status}`)}</Badge>,
    },
    {
      key: "total_amount",
      header: t("purchasing.orders.total"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.total_amount),
      render: (r) => formatCurrency(r.total_amount),
    },
  ];

  return (
    <ERPListView
      title={t("purchasing.orders.title")}
      columns={columns}
      rows={orders}
      rowKey={(r) => r.id}
      getRowHref={(r) => `/purchasing/orders/${r.id}`}
      isLoading={ordersQuery.isLoading}
      isError={ordersQuery.isError}
      errorMessage={ordersQuery.error instanceof ApiError ? ordersQuery.error.detail : undefined}
      onRetry={() => ordersQuery.refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["purchase-orders", companyId] })}
      searchText={(r) => `${r.number} ${vendorLabel(r.partner_id)}`}
      searchPlaceholder={t("list.search_placeholder")}
      emptyDescription={t("purchasing.orders.empty_description")}
      createAction={{
        label: t("purchasing.orders.new"),
        href: "/purchasing/orders/new",
        permission: "purchasing.order.create",
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

function VendorBillsTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const { label: vendorLabel } = useVendorLabel();
  const [filters, setFilters] = useState<Record<string, string>>({});

  const billsQuery = useQuery({
    queryKey: ["vendor-bills", companyId, filters.status, filters.date_from, filters.date_to],
    queryFn: () =>
      purchasingApi.listVendorBills(companyId, {
        status: filters.status || undefined,
        dateFrom: filters.date_from || undefined,
        dateTo: filters.date_to || undefined,
        pageSize: 200,
      }),
  });
  const bills = billsQuery.data?.items;

  const filterFields: FilterFieldConfig[] = [
    {
      key: "status",
      label: t("purchasing.orders.status"),
      type: "select",
      options: BILL_STATUSES.map((s) => ({ value: s, label: s })),
      width: "w-44",
    },
    { key: "date_from", label: t("sales.reports.date_from"), type: "date" },
    { key: "date_to", label: t("sales.reports.date_to"), type: "date" },
  ];

  const approveMutation = useMutation({
    mutationFn: (id: string) => purchasingApi.approveVendorBill(companyId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] });
      toastSuccess(t("toast.success_title"), t("purchasing.vendor_bills.approve"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const columns: ERPColumn<VendorBill>[] = [
    { key: "number", header: t("purchasing.orders.number"), sortable: true, sortValue: (r) => r.number, render: (r) => r.number },
    { key: "vendor", header: t("purchasing.orders.vendor"), render: (r) => vendorLabel(r.partner_id) },
    {
      key: "bill_type",
      header: t("purchasing.vendor_bills.type"),
      render: (r) =>
        r.bill_type === "debit_note" ? (
          <Badge variant="warning">{t("purchasing.vendor_bills.type_debit_note")}</Badge>
        ) : (
          <span className="text-muted-foreground">{t("purchasing.vendor_bills.type_standard")}</span>
        ),
    },
    {
      key: "status",
      header: t("purchasing.orders.status"),
      render: (r) => (
        <div className="flex gap-1">
          <Badge variant={statusVariant(r.status)}>{r.status}</Badge>
          {r.mismatch_reasons && <Badge variant="destructive">{t("purchasing.vendor_bills.mismatch")}</Badge>}
        </div>
      ),
    },
    {
      key: "total_amount",
      header: t("purchasing.orders.total"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.total_amount),
      render: (r) => formatCurrency(r.total_amount),
    },
  ];

  return (
    <ERPListView
      title={t("purchasing.vendor_bills.title")}
      columns={columns}
      rows={bills}
      rowKey={(r) => r.id}
      isLoading={billsQuery.isLoading}
      isError={billsQuery.isError}
      errorMessage={billsQuery.error instanceof ApiError ? billsQuery.error.detail : undefined}
      onRetry={() => billsQuery.refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] })}
      searchText={(r) => `${r.number} ${vendorLabel(r.partner_id)}`}
      searchPlaceholder={t("list.search_placeholder")}
      emptyDescription={t("purchasing.vendor_bills.empty_description")}
      getRowHref={(r) => `/purchasing/bills/${r.id}`}
      rowActions={(r) =>
        r.status !== "posted" && (
          <Can permission="purchasing.vendor_bill.approve">
            <Button size="sm" variant="outline" onClick={() => approveMutation.mutate(r.id)} disabled={approveMutation.isPending}>
              {t("purchasing.vendor_bills.approve")}
            </Button>
          </Can>
        )
      }
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

export default function PurchasingPage() {
  const { t } = useI18n();
  // See the same note in accounting/page.tsx — Base UI's Tabs.Panel doesn't
  // reliably hide inactive panels once a second one mounts, so the active
  // tab is tracked ourselves and gates each panel's content directly.
  const [tab, setTab] = useState("orders");
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t("nav.purchasing")}</h1>
      <Tabs value={tab} onValueChange={(v) => setTab(v as string)}>
        <TabsList>
          <TabsTrigger value="orders">{t("purchasing.orders.title")}</TabsTrigger>
          <TabsTrigger value="bills">{t("purchasing.vendor_bills.title")}</TabsTrigger>
        </TabsList>
        <TabsContent value="orders">{tab === "orders" && <OrdersTab />}</TabsContent>
        <TabsContent value="bills">{tab === "bills" && <VendorBillsTab />}</TabsContent>
      </Tabs>
    </div>
  );
}
