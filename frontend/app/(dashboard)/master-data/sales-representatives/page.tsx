"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Breadcrumbs } from "@/components/erp/breadcrumbs/breadcrumbs";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import type { SalesRepresentative } from "@/features/identity/api/types";
import { ApiError } from "@/lib/api-client";

export default function SalesRepresentativesPage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const salesRepsQuery = useQuery({
    queryKey: ["sales-representatives", companyId, "all"],
    queryFn: () => identityApi.listSalesRepresentatives(companyId),
  });

  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [commissionRate, setCommissionRate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      identityApi.createSalesRepresentative(companyId, {
        name,
        code,
        commission_rate: commissionRate || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales-representatives", companyId] });
      setName("");
      setCode("");
      setCommissionRate("");
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: (rep: SalesRepresentative) =>
      identityApi.updateSalesRepresentative(companyId, rep.id, {
        name: rep.name,
        code: rep.code,
        commission_rate: rep.commission_rate,
        is_active: !rep.is_active,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sales-representatives", companyId] }),
  });

  const columns: ERPColumn<SalesRepresentative>[] = [
    { key: "code", header: t("master_data.sales_representatives.code"), sortable: true, sortValue: (r) => r.code, render: (r) => <span className="font-mono">{r.code}</span> },
    { key: "name", header: t("master_data.sales_representatives.name"), sortable: true, sortValue: (r) => r.name, render: (r) => r.name },
    {
      key: "commission_rate",
      header: t("master_data.sales_representatives.commission_rate"),
      sortable: true,
      sortValue: (r) => Number(r.commission_rate ?? 0),
      render: (r) => (r.commission_rate ? `${r.commission_rate}%` : "—"),
    },
    {
      key: "is_active",
      header: t("master_data.sales_representatives.active"),
      sortable: true,
      sortValue: (r) => (r.is_active ? 1 : 0),
      render: (r) => <Badge variant={r.is_active ? "default" : "secondary"}>{r.is_active ? t("common.active") : t("common.inactive")}</Badge>,
    },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: t("nav.master_data") }, { label: t("master_data.sales_representatives.title") }]} />
      <h1 className="text-2xl font-semibold">{t("master_data.sales_representatives.title")}</h1>

      <Can permission="sales_rep.create">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("master_data.sales_representatives.new")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label className="text-xs">{t("master_data.sales_representatives.code")}</Label>
                <Input value={code} onChange={(e) => setCode(e.target.value)} className="w-28" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("master_data.sales_representatives.name")}</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("master_data.sales_representatives.commission_rate")}</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={commissionRate}
                  onChange={(e) => setCommissionRate(e.target.value)}
                  className="w-32"
                />
              </div>
              <Button
                size="sm"
                onClick={() => {
                  setError(null);
                  createMutation.mutate();
                }}
                disabled={!name || !code || createMutation.isPending}
              >
                <Plus className="h-4 w-4" />
                {t("common.save")}
              </Button>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </Can>

      <ERPListView
        title={t("master_data.sales_representatives.list_title")}
        columns={columns}
        rows={salesRepsQuery.data}
        rowKey={(r) => r.id}
        isLoading={salesRepsQuery.isLoading}
        isError={salesRepsQuery.isError}
        onRetry={() => salesRepsQuery.refetch()}
        searchText={(r) => `${r.code} ${r.name}`}
        searchPlaceholder={t("list.search_placeholder")}
        rowActions={(r) => (
          <Can permission="sales_rep.update">
            <Button variant="ghost" size="xs" onClick={() => toggleActiveMutation.mutate(r)} disabled={toggleActiveMutation.isPending}>
              {r.is_active ? t("master_data.sales_representatives.deactivate") : t("master_data.sales_representatives.activate")}
            </Button>
          </Can>
        )}
      />
    </div>
  );
}
