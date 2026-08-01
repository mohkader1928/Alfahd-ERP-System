"use client";

import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import type { Partner } from "@/features/identity/api/types";
import { ApiError } from "@/lib/api-client";

/**
 * Phase 17B: shared list for both Customers and Vendors — same Partner
 * backend entity, filtered by `kind`, so the two nav entries don't
 * duplicate table/column/search logic (per the Phase 17B brief's explicit
 * "share a reusable PartnerListView" requirement).
 */
export function PartnerListView({ kind }: { kind: "customer" | "vendor" }) {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const queryClient = useQueryClient();

  const title = kind === "customer" ? t("master_data.customers.title") : t("master_data.vendors.title");
  const newLabel = kind === "customer" ? t("master_data.customers.new") : t("master_data.vendors.new");

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["partners", companyId, kind],
    queryFn: () =>
      identityApi.listPartners(companyId, branchId, {
        customersOnly: kind === "customer",
        vendorsOnly: kind === "vendor",
      }),
  });

  const columns: ERPColumn<Partner>[] = [
    {
      key: "name",
      header: t("master_data.partners.name"),
      sortable: true,
      sortValue: (r) => r.name,
      render: (r) => (
        <Link href={`/master-data/partners/${r.id}`} className="font-medium underline-offset-4 hover:underline">
          {r.name}
        </Link>
      ),
    },
    { key: "name_ar", header: t("master_data.partners.name_ar"), render: (r) => r.name_ar ?? "—" },
    { key: "vat_number", header: t("master_data.partners.vat_number"), render: (r) => r.vat_number ?? "—" },
    { key: "cr_number", header: t("master_data.partners.cr_number"), render: (r) => r.cr_number ?? "—" },
    {
      key: "is_active",
      header: t("master_data.partners.status"),
      render: (r) => <Badge variant={r.is_active ? "default" : "secondary"}>{r.is_active ? t("common.active") : t("common.inactive")}</Badge>,
    },
  ];

  return (
    <ERPListView
      title={title}
      breadcrumbs={[{ label: t("nav.master_data") }, { label: title }]}
      columns={columns}
      rows={data}
      rowKey={(r) => r.id}
      isLoading={isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["partners", companyId, kind] })}
      searchText={(r) => `${r.name} ${r.name_ar ?? ""} ${r.vat_number ?? ""} ${r.cr_number ?? ""}`}
      searchPlaceholder={t("list.search_placeholder")}
      createAction={{
        label: newLabel,
        href: `/master-data/partners/new?kind=${kind}`,
        permission: "partner.create",
      }}
    />
  );
}
