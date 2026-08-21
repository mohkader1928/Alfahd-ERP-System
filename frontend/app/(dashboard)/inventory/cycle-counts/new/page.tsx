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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EntitySearchSelect } from "@/components/erp/entity-search-select/entity-search-select";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { toastError, toastSuccess } from "@/lib/toast";

interface Line {
  product_id: string;
  location_id: string;
  system_qty: string;
  counted_qty: string;
  /** True for a row the warehouse's own stock balance produced -- vs one
   * the user added manually for a product that isn't (yet) part of that
   * balance, e.g. found physically where the books show nothing. */
  auto: boolean;
}

// Owner request: picking a warehouse should pre-populate the count sheet
// with every product the warehouse's own book balance says is on hand --
// System Qty visible right next to an editable Actual Qty the user fills
// in during the physical count -- instead of starting from a blank
// product-by-product picker with no balance in sight. Manual add-line
// stays available underneath for a product physically found where the
// books show nothing.
export default function NewCycleCountPage() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);

  const [warehouseId, setWarehouseId] = useState("");
  const [scheduledDate, setScheduledDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [lines, setLines] = useState<Line[]>([]);
  const [loadedWarehouseId, setLoadedWarehouseId] = useState<string | null>(null);
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
  const quantsQuery = useQuery({
    queryKey: ["stock-quants", companyId, warehouseId],
    queryFn: () => inventoryApi.listStockQuants(companyId, warehouseId),
    enabled: !!warehouseId,
  });

  // Same "conditional setState during render" reset pattern already used
  // elsewhere in this codebase (e.g. sales/purchasing returns) for
  // re-deriving local state when a freshly-fetched external source
  // changes -- fires once per newly selected warehouse.
  if (quantsQuery.data && warehouseId && warehouseId !== loadedWarehouseId) {
    setLoadedWarehouseId(warehouseId);
    setLines(
      quantsQuery.data.map((q) => ({
        product_id: q.product_id,
        location_id: q.location_id,
        system_qty: q.qty_on_hand,
        counted_qty: q.qty_on_hand,
        auto: true,
      }))
    );
  }

  const createMutation = useMutation({
    mutationFn: () =>
      inventoryApi.createCycleCount(companyId, {
        warehouse_id: warehouseId,
        scheduled_date: scheduledDate,
        lines: lines.map((l) => ({
          product_id: l.product_id,
          location_id: l.location_id,
          counted_qty: l.counted_qty,
        })),
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

  async function updateManualProduct(index: number, productId: string) {
    updateLine(index, { product_id: productId });
    const location = lines[index].location_id;
    if (!productId || !location) return;
    try {
      const balance = await inventoryApi.getStockBalanceByProduct(companyId, productId);
      const row = balance.by_warehouse.find((w) => w.warehouse_id === warehouseId);
      updateLine(index, { product_id: productId, system_qty: row?.qty_on_hand ?? "0" });
    } catch {
      // Balance lookup is a convenience -- a manual line still submits fine without it.
    }
  }

  function addManualLine() {
    setLines((prev) => [...prev, { product_id: "", location_id: "", system_qty: "0", counted_qty: "0", auto: false }]);
  }

  function removeLine(index: number) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  const productLabel = (productId: string) => {
    const p = productsQuery.data?.find((prod) => prod.id === productId);
    return p ? `${p.sku} — ${locale === "ar" && p.name_ar ? p.name_ar : p.name}` : productId;
  };
  const locationLabel = (locationId: string) => locationsQuery.data?.find((l) => l.id === locationId)?.name ?? locationId;

  const canSave =
    !!warehouseId && lines.length > 0 && lines.every((l) => l.product_id && l.location_id && l.counted_qty !== "");

  return (
    <div className="max-w-3xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/inventory?tab=cycle-counts")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{t("inventory.cycle_counts.create_title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4">
            <div className="w-64 space-y-2">
              <Label>{t("inventory.stock.warehouse")}</Label>
              <Select
                value={warehouseId}
                onValueChange={(v) => {
                  setWarehouseId(v ?? "");
                  setLines([]);
                  setLoadedWarehouseId(null);
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
          </div>

          {!warehouseId && (
            <p className="text-sm text-muted-foreground">{t("inventory.cycle_counts.select_warehouse_hint")}</p>
          )}

          {warehouseId && quantsQuery.isLoading && (
            <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
          )}

          {warehouseId && !quantsQuery.isLoading && (
            <div className="space-y-2">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("inventory.stock.product")}</TableHead>
                    <TableHead>{t("inventory.cycle_counts.location")}</TableHead>
                    <TableHead className="text-end">{t("inventory.cycle_counts.system_qty")}</TableHead>
                    <TableHead className="w-32 text-end">{t("inventory.cycle_counts.counted_qty")}</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lines.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-muted-foreground">
                        {t("inventory.cycle_counts.no_balance_hint")}
                      </TableCell>
                    </TableRow>
                  )}
                  {lines.map((line, index) => {
                    const variance = line.counted_qty !== "" ? Number(line.counted_qty) - Number(line.system_qty) : 0;
                    return (
                      <TableRow key={index}>
                        <TableCell>
                          {line.auto ? (
                            productLabel(line.product_id)
                          ) : (
                            <EntitySearchSelect
                              items={(productsQuery.data ?? []).map((p) => ({
                                id: p.id,
                                label: p.name,
                                code: p.sku,
                                searchText: `${p.sku} ${p.name} ${p.name_ar ?? ""}`,
                              }))}
                              value={line.product_id || null}
                              onChange={(v) => updateManualProduct(index, v ?? "")}
                              placeholder={t("inventory.stock.product")}
                            />
                          )}
                        </TableCell>
                        <TableCell>
                          {line.auto ? (
                            locationLabel(line.location_id)
                          ) : (
                            <Select
                              value={line.location_id}
                              onValueChange={(v) => updateLine(index, { location_id: v ?? "" })}
                            >
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
                          )}
                        </TableCell>
                        <TableCell className="text-end font-mono tabular-nums text-muted-foreground">
                          {line.system_qty}
                        </TableCell>
                        <TableCell>
                          <Input
                            className={cn(
                              "text-end font-mono tabular-nums",
                              variance !== 0 && "border-destructive text-destructive"
                            )}
                            value={line.counted_qty}
                            onChange={(e) => updateLine(index, { counted_qty: e.target.value })}
                          />
                        </TableCell>
                        <TableCell>
                          <Button type="button" variant="ghost" size="icon" onClick={() => removeLine(index)}>
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              <Button type="button" variant="outline" size="sm" onClick={addManualLine}>
                <Plus className="h-4 w-4" />
                {t("inventory.cycle_counts.add_manual_line")}
              </Button>
            </div>
          )}

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
