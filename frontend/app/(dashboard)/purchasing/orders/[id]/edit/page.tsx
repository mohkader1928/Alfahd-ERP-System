"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { EntitySearchSelect } from "@/components/erp/entity-search-select/entity-search-select";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import { identityApi } from "@/features/identity/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";

interface Line {
  product_id: string;
  qty: string;
  unit_price: string;
}

// Product Owner request: allow editing a transaction before it's
// posted/confirmed — a Purchase Order's own 'draft' status is exactly
// that window, gated server-side (qty_received/qty_billed are guaranteed
// zero on every line until confirmed).
export default function EditPurchaseOrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [orderDate, setOrderDate] = useState("");
  const [taxRateId, setTaxRateId] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Not a useEffect: React's own guidance for "adjust state when data
  // arrives" is to compare against the previous render's id during render
  // itself, not sync it in an effect.
  const [loadedForId, setLoadedForId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["purchase-order", companyId, id],
    queryFn: () => purchasingApi.getOrder(companyId, id),
  });
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
  const effectiveTaxRateId =
    taxRateId || taxRatesQuery.data?.find((r) => r.kind === "standard")?.id || "";

  if (data && loadedForId !== id) {
    setPartnerId(data.order.partner_id);
    setOrderDate(data.order.order_date);
    setLines(
      data.lines.length > 0
        ? data.lines.map((l) => ({ product_id: l.product_id, qty: l.qty, unit_price: l.unit_price }))
        : [{ product_id: "", qty: "1", unit_price: "0" }]
    );
    setLoadedForId(id);
  }
  const loaded = loadedForId === id;

  const updateMutation = useMutation({
    mutationFn: () =>
      purchasingApi.updateOrder(companyId, branchId, id, {
        partner_id: partnerId,
        order_date: orderDate,
        lines: lines.map((l) => ({ ...l, tax_rate_id: effectiveTaxRateId })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["purchase-order", companyId, id] });
      queryClient.invalidateQueries({ queryKey: ["purchase-orders", companyId] });
      router.push(`/purchasing/orders/${id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
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

  if (isLoading || !loaded) return <Skeleton className="h-60 w-full" />;
  if (!data) return null;
  const { order } = data;
  if (order.status !== "draft") {
    return (
      <div className="max-w-xl space-y-4">
        <Button variant="ghost" size="sm" onClick={() => router.push(`/purchasing/orders/${id}`)}>
          <ArrowLeft className="h-4 w-4" />
          {t("common.back")}
        </Button>
        <p className="text-sm text-muted-foreground">{t("purchasing.orders.edit_locked")}</p>
      </div>
    );
  }

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push(`/purchasing/orders/${id}`)}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>
            {t("common.edit")} — {order.number}
          </CardTitle>
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
                      updateLine(index, {
                        product_id: v ?? "",
                        unit_price: product?.last_purchase_price ?? line.unit_price,
                      });
                    }}
                    placeholder={t("purchasing.orders.select_product")}
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
              updateMutation.mutate();
            }}
            disabled={!partnerId || !effectiveTaxRateId || updateMutation.isPending}
          >
            {updateMutation.isPending ? t("common.loading") : t("common.save")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
