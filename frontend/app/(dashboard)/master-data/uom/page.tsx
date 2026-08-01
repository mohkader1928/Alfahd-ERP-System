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
import type { UnitOfMeasure } from "@/features/identity/api/types";
import { ApiError } from "@/lib/api-client";

export default function UnitsOfMeasurePage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const uomQuery = useQuery({
    queryKey: ["uom", companyId, "all"],
    queryFn: () => identityApi.listUom(companyId),
  });

  const [name, setName] = useState("");
  const [nameAr, setNameAr] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => identityApi.createUom(companyId, { name, name_ar: nameAr || null, code }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["uom", companyId] });
      setName("");
      setNameAr("");
      setCode("");
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: (uom: UnitOfMeasure) =>
      identityApi.updateUom(companyId, uom.id, {
        name: uom.name,
        name_ar: uom.name_ar,
        code: uom.code,
        active: !uom.active,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["uom", companyId] }),
  });

  const columns: ERPColumn<UnitOfMeasure>[] = [
    { key: "code", header: t("master_data.uom.code"), sortable: true, sortValue: (r) => r.code, render: (r) => <span className="font-mono">{r.code}</span> },
    { key: "name", header: t("master_data.uom.name"), sortable: true, sortValue: (r) => r.name, render: (r) => r.name },
    { key: "name_ar", header: t("master_data.uom.name_ar"), render: (r) => r.name_ar ?? "—" },
    {
      key: "active",
      header: t("master_data.uom.active"),
      render: (r) => <Badge variant={r.active ? "default" : "secondary"}>{r.active ? t("common.active") : t("common.inactive")}</Badge>,
    },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: t("nav.master_data") }, { label: t("master_data.uom.title") }]} />
      <h1 className="text-2xl font-semibold">{t("master_data.uom.title")}</h1>

      <Can permission="uom.manage">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("master_data.uom.new")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label className="text-xs">{t("master_data.uom.code")}</Label>
                <Input value={code} onChange={(e) => setCode(e.target.value)} className="w-28" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("master_data.uom.name")}</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("master_data.uom.name_ar")}</Label>
                <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" className="w-48" />
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
        title={t("master_data.uom.list_title")}
        columns={columns}
        rows={uomQuery.data}
        rowKey={(r) => r.id}
        isLoading={uomQuery.isLoading}
        isError={uomQuery.isError}
        onRetry={() => uomQuery.refetch()}
        searchText={(r) => `${r.code} ${r.name} ${r.name_ar ?? ""}`}
        searchPlaceholder={t("list.search_placeholder")}
        rowActions={(r) => (
          <Can permission="uom.manage">
            <Button variant="ghost" size="xs" onClick={() => toggleActiveMutation.mutate(r)} disabled={toggleActiveMutation.isPending}>
              {r.active ? t("master_data.uom.deactivate") : t("master_data.uom.activate")}
            </Button>
          </Can>
        )}
      />
    </div>
  );
}
