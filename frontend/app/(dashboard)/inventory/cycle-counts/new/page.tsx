"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EntitySearchSelect } from "@/components/erp/entity-search-select/entity-search-select";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";

interface Line {
  product_id: string;
  location_id: string;
  counted_qty: string;
}

export default function NewCycleCountPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);

  const [warehouseId, setWarehouseId] = useState("");
  const [scheduledDate, setScheduledDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [lines, setLines] = useState<Line[]>([{ product_id: "", location_id: "", counted_qty: "0" }]);
  const [error, setError] = useState<string | null>(null);

  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });
  const locationsQuery = useQuery({
    queryKey: ["locations", companyId, warehouseId],
    queryFn: () => inventoryApi.listLocations(companyId, warehouseId),
    enabled: !!warehouseId,
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      inventoryApi.createCycleCount(companyId, {
        warehouse_id: warehouseId,
        scheduled_date: scheduledDate,
        lines,
      }),
    onSuccess: (detail) => {
      queryClient.invalidateQueries({ queryKey: ["cycle-counts", companyId] });
      toastSuccess(t("toast.success_title"), t("inventory.cycle_counts.save"));
      router.push(`/inventory/cycle-counts/${detail.cycle_count.id}`);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  function updateLine(index: number, patch: Partial<Line>) {
    setLines((prev) => prev.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  function addLine() {
    setLines((prev) => [...prev, { product_id: "", location_id: "", counted_qty: "0" }]);
  }

  function removeLine(index: number) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  const canSave = !!warehouseId && lines.every((l) => l.product_id && l.location_id);

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/inventory?tab=cycle-counts")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{t("inventory.cycle_counts.create_title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>{t("inventory.stock.warehouse")}</Label>
            <Select
              value={warehouseId}
              onValueChange={(v) => {
                setWarehouseId(v ?? "");
                setLines((prev) => prev.map((line) => ({ ...line, location_id: "" })));
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("inventory.stock.warehouse")}>
                  {(value: string) => warehousesQuery.data?.find((w) => w.id === value)?.name ?? value}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {warehousesQuery.data?.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>{t("inventory.cycle_counts.scheduled_date")}</Label>
            <Input type="date" value={scheduledDate} onChange={(e) => setScheduledDate(e.target.value)} />
          </div>
          <div className="space-y-2">
            {lines.map((line, index) => (
              <div key={index} className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  <Label className="text-xs">{t("inventory.stock.product")}</Label>
                  <EntitySearchSelect
                    items={(productsQuery.data ?? []).map((p) => ({
                      id: p.id,
                      label: p.name,
                      code: p.sku,
                      searchText: `${p.sku} ${p.name} ${p.name_ar ?? ""}`,
                    }))}
                    value={line.product_id || null}
                    onChange={(v) => updateLine(index, { product_id: v ?? "" })}
                    placeholder={t("inventory.stock.product")}
                  />
                </div>
                <div className="w-36 space-y-1">
                  <Label className="text-xs">{t("inventory.cycle_counts.location")}</Label>
                  <Select value={line.location_id} onValueChange={(v) => updateLine(index, { location_id: v ?? "" })}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t("inventory.cycle_counts.location")}>
                        {(value: string) => locationsQuery.data?.find((l) => l.id === value)?.name ?? value}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {locationsQuery.data?.map((l) => (
                        <SelectItem key={l.id} value={l.id}>
                          {l.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="w-28 space-y-1">
                  <Label className="text-xs">{t("inventory.cycle_counts.counted_qty")}</Label>
                  <Input value={line.counted_qty} onChange={(e) => updateLine(index, { counted_qty: e.target.value })} />
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => removeLine(index)}
                  disabled={lines.length === 1}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={addLine} disabled={!warehouseId}>
              <Plus className="h-4 w-4" />
              {t("purchasing.orders.add_line")}
            </Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!canSave || createMutation.isPending}
          >
            {createMutation.isPending ? t("common.loading") : t("inventory.cycle_counts.save")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
