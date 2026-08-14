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
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { EntitySearchSelect } from "@/components/erp/entity-search-select/entity-search-select";
import { StockBalanceHint } from "@/components/erp/stock-balance-hint/stock-balance-hint";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";

interface Line {
  product_id: string;
  qty: string;
  unit_price: string;
}

export default function NewPurchaseOrderPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [orderDate, setOrderDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [taxRateId, setTaxRateId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [lines, setLines] = useState<Line[]>([{ product_id: "", qty: "1", unit_price: "0" }]);
  const [error, setError] = useState<string | null>(null);

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "vendors"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  const taxRatesQuery = useQuery({
    queryKey: ["tax-rates", companyId],
    queryFn: () => accountingApi.listTaxRates(companyId),
  });
  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });
  const effectiveTaxRateId =
    taxRateId || taxRatesQuery.data?.find((r) => r.kind === "standard")?.id || "";
  const effectiveWarehouseId =
    warehouseId || warehousesQuery.data?.find((w) => w.is_default)?.id || "";

  const createMutation = useMutation({
    mutationFn: () =>
      purchasingApi.createOrder(companyId, branchId, {
        partner_id: partnerId,
        order_date: orderDate,
        warehouse_id: effectiveWarehouseId || null,
        lines: lines.map((l) => ({ ...l, tax_rate_id: effectiveTaxRateId })),
      }),
    onSuccess: (order) => {
      queryClient.invalidateQueries({ queryKey: ["purchase-orders", companyId] });
      toastSuccess(t("toast.success_title"), order.number);
      router.push(`/purchasing/orders/${order.id}`);
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
    setLines((prev) => [...prev, { product_id: "", qty: "1", unit_price: "0" }]);
  }

  function removeLine(index: number) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/purchasing")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{t("purchasing.orders.create_title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>{t("purchasing.orders.vendor")}</Label>
            <Select value={partnerId} onValueChange={(v) => setPartnerId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("purchasing.orders.select_vendor")}>
                  {(value: string) => {
                    const partner = partnersQuery.data?.find((p) => p.id === value);
                    return partner ? (
                      <span className="flex items-center gap-2">
                        <EntityImage src={partner.image_path} name={partner.name} size="xs" />
                        {partner.name}
                      </span>
                    ) : (
                      value
                    );
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {partnersQuery.data?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    <span className="flex items-center gap-2">
                      <EntityImage src={p.image_path} name={p.name} size="xs" />
                      {p.name}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>{t("purchasing.orders.date")}</Label>
            <Input type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>{t("inventory.stock.warehouse")}</Label>
            <Select value={effectiveWarehouseId} onValueChange={(v) => setWarehouseId(v ?? "")}>
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
            <Label>{t("common.tax_rate")}</Label>
            <Select value={effectiveTaxRateId} onValueChange={(v) => setTaxRateId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("common.select_tax_rate")}>
                  {(value: string) => {
                    const rate = taxRatesQuery.data?.find((r) => r.id === value);
                    return rate ? `${rate.name} (${rate.rate_percent}%)` : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {taxRatesQuery.data?.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.name} ({r.rate_percent}%)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            {lines.map((line, index) => (
              <div key={index} className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  <Label className="text-xs">{t("purchasing.orders.select_product")}</Label>
                  <EntitySearchSelect
                    items={(productsQuery.data ?? []).map((p) => ({
                      id: p.id,
                      label: p.name,
                      code: p.sku,
                      searchText: `${p.sku} ${p.name} ${p.name_ar ?? ""}`,
                      imageSrc: p.image_path,
                      imageShape: "square" as const,
                    }))}
                    value={line.product_id || null}
                    onChange={(v) => {
                      const product = productsQuery.data?.find((p) => p.id === v);
                      // Owner-requested default: picking a product pre-fills
                      // the line price from its last purchase price instead
                      // of leaving the buyer typing "0" from scratch.
                      updateLine(index, {
                        product_id: v ?? "",
                        unit_price: product?.last_purchase_price ?? line.unit_price,
                      });
                    }}
                    placeholder={t("purchasing.orders.select_product")}
                  />
                  <StockBalanceHint
                    companyId={companyId}
                    productId={line.product_id}
                    warehouseId={effectiveWarehouseId}
                  />
                </div>
                <div className="w-20 space-y-1">
                  <Label className="text-xs">{t("purchasing.orders.qty")}</Label>
                  <Input value={line.qty} onChange={(e) => updateLine(index, { qty: e.target.value })} />
                </div>
                <div className="w-24 space-y-1">
                  <Label className="text-xs">{t("purchasing.orders.unit_price")}</Label>
                  <Input value={line.unit_price} onChange={(e) => updateLine(index, { unit_price: e.target.value })} />
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
            <Button type="button" variant="outline" size="sm" onClick={addLine}>
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
            disabled={!partnerId || !effectiveTaxRateId || createMutation.isPending}
          >
            {createMutation.isPending ? t("common.loading") : t("purchasing.orders.save")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
