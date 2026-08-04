"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import type { Partner } from "@/features/identity/api/types";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";

export type PartnerListKind = "customer" | "vendor" | "employee" | "all";

/**
 * Unified Address Book bundle: Address Book (kind="all"), Customers,
 * Vendors, and Employees are all this same list — just different filters
 * over the one Partner table, per the Owner's condition that these must be
 * VIEWS on shared master data, not separate screens. Company/Individual
 * and Active/Archived filters, plus (Address Book only) a Role filter,
 * satisfy the "real ERP list" checklist — search/sort/pagination were
 * already covered by ERPListView itself.
 */
export function PartnerListView({ kind }: { kind: PartnerListKind }) {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const queryClient = useQueryClient();

  const [companyFilter, setCompanyFilter] = useState<"all" | "company" | "individual">("all");
  const [statusFilter, setStatusFilter] = useState<"active" | "archived" | "all">("active");
  const [roleFilter, setRoleFilter] = useState<"all" | "customer" | "vendor" | "employee" | "contact">("all");

  const titleKey = {
    customer: "master_data.customers.title",
    vendor: "master_data.vendors.title",
    employee: "master_data.employees.title",
    all: "master_data.address_book.title",
  }[kind];
  const newLabelKey = {
    customer: "master_data.customers.new",
    vendor: "master_data.vendors.new",
    employee: "master_data.employees.new",
    all: "master_data.address_book.new",
  }[kind];
  const emptyKey = {
    customer: "master_data.customers.empty_description",
    vendor: "master_data.vendors.empty_description",
    employee: "master_data.employees.empty_description",
    all: "master_data.address_book.empty_description",
  }[kind];
  const title = t(titleKey);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["partners", companyId, kind, statusFilter],
    queryFn: () =>
      identityApi.listPartners(companyId, branchId, {
        customersOnly: kind === "customer",
        vendorsOnly: kind === "vendor",
        employeesOnly: kind === "employee",
        includeArchived: statusFilter !== "active",
      }),
  });

  const rows = useMemo(() => {
    if (!data) return data;
    let filtered = data;
    if (statusFilter === "archived") filtered = filtered.filter((p) => !p.is_active);
    if (companyFilter !== "all") filtered = filtered.filter((p) => (companyFilter === "company" ? p.is_company : !p.is_company));
    if (kind === "all" && roleFilter !== "all") {
      filtered = filtered.filter((p) => {
        if (roleFilter === "customer") return p.is_customer;
        if (roleFilter === "vendor") return p.is_vendor;
        if (roleFilter === "employee") return p.is_employee;
        return !p.is_customer && !p.is_vendor && !p.is_employee;
      });
    }
    return filtered;
  }, [data, statusFilter, companyFilter, roleFilter, kind]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["partners", companyId, kind, statusFilter] });

  const archiveMutation = useMutation({
    mutationFn: (p: Partner) => identityApi.archivePartner(companyId, p.id),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("master_data.partners.archived"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const restoreMutation = useMutation({
    mutationFn: (p: Partner) => identityApi.restorePartner(companyId, p.id),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("master_data.partners.restored"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const columns: ERPColumn<Partner>[] = [
    {
      key: "name",
      header: t("master_data.partners.name"),
      sortable: true,
      sortValue: (r) => r.name,
      render: (r) => (
        <Link href={`/master-data/partners/${r.id}`} className="flex items-center gap-2 font-medium underline-offset-4 hover:underline">
          <EntityImage src={r.image_path} name={r.name} size="xs" />
          {r.name}
          {!r.is_company && <span className="text-xs font-normal text-muted-foreground">({t("master_data.partners.individual")})</span>}
        </Link>
      ),
    },
    { key: "name_ar", header: t("master_data.partners.name_ar"), render: (r) => r.name_ar ?? "—" },
    {
      key: "roles",
      header: t("master_data.partners.roles"),
      render: (r) => (
        <div className="flex flex-wrap gap-1">
          {r.is_customer && <Badge variant="outline">{t("master_data.partners.is_customer")}</Badge>}
          {r.is_vendor && <Badge variant="outline">{t("master_data.partners.is_vendor")}</Badge>}
          {r.is_employee && <Badge variant="outline">{t("master_data.partners.is_employee")}</Badge>}
          {!r.is_customer && !r.is_vendor && !r.is_employee && <span className="text-muted-foreground">—</span>}
        </div>
      ),
    },
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
      rows={rows}
      rowKey={(r) => r.id}
      getRowHref={(r) => `/master-data/partners/${r.id}`}
      isLoading={isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={invalidate}
      searchText={(r) => `${r.name} ${r.name_ar ?? ""} ${r.vat_number ?? ""} ${r.cr_number ?? ""} ${r.email ?? ""} ${r.phone ?? ""}`}
      searchPlaceholder={t("list.search_placeholder")}
      emptyDescription={t(emptyKey)}
      filters={
        <>
          <Select value={companyFilter} onValueChange={(v) => setCompanyFilter((v as typeof companyFilter) ?? "all")}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder={t("master_data.partners.filter_company_individual")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("master_data.partners.filter_all")}</SelectItem>
              <SelectItem value="company">{t("master_data.partners.filter_company")}</SelectItem>
              <SelectItem value="individual">{t("master_data.partners.filter_individual")}</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter((v as typeof statusFilter) ?? "active")}>
            <SelectTrigger className="w-36">
              <SelectValue placeholder={t("master_data.partners.status")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="active">{t("common.active")}</SelectItem>
              <SelectItem value="archived">{t("master_data.partners.archived_filter")}</SelectItem>
              <SelectItem value="all">{t("master_data.partners.filter_all")}</SelectItem>
            </SelectContent>
          </Select>
          {kind === "all" && (
            <Select value={roleFilter} onValueChange={(v) => setRoleFilter((v as typeof roleFilter) ?? "all")}>
              <SelectTrigger className="w-40">
                <SelectValue placeholder={t("master_data.partners.roles")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("master_data.partners.filter_all")}</SelectItem>
                <SelectItem value="customer">{t("master_data.partners.is_customer")}</SelectItem>
                <SelectItem value="vendor">{t("master_data.partners.is_vendor")}</SelectItem>
                <SelectItem value="employee">{t("master_data.partners.is_employee")}</SelectItem>
                <SelectItem value="contact">{t("master_data.partners.filter_contact_only")}</SelectItem>
              </SelectContent>
            </Select>
          )}
        </>
      }
      createAction={{
        label: t(newLabelKey),
        href: `/master-data/partners/new?kind=${kind === "all" ? "customer" : kind}`,
        permission: "partner.create",
      }}
      rowActions={(r) => (
        <Can permission="partner.update">
          {r.is_active ? (
            <Button variant="ghost" size="xs" onClick={() => archiveMutation.mutate(r)} disabled={archiveMutation.isPending}>
              {t("master_data.partners.archive")}
            </Button>
          ) : (
            <Button variant="ghost" size="xs" onClick={() => restoreMutation.mutate(r)} disabled={restoreMutation.isPending}>
              {t("master_data.partners.restore")}
            </Button>
          )}
        </Can>
      )}
    />
  );
}
