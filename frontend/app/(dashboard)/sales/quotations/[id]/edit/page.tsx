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
import { Textarea } from "@/components/ui/textarea";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { EntitySearchSelect } from "@/components/erp/entity-search-select/entity-search-select";
import { StockBalanceHint } from "@/components/erp/stock-balance-hint/stock-balance-hint";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { salesApi } from "@/features/sales/api/client";
import { ApiError } from "@/lib/api-client";

interface Line {
  product_id: string;
  qty: string;
  unit_price: string;
}

// Product Owner request: allow editing a transaction before it's
// posted/confirmed. A Quotation is the one genuinely pre-commitment stage
// in Sales (an Order is created already 'confirmed'; an Invoice is
// created+submitted+journaled atomically with no draft window) — so this
// is the edit surface for that stage, gated server-side to status='draft'.
export default function EditQuotationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [quoteDate, setQuoteDate] = useState("");
  const [taxRateId, setTaxRateId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [paymentTerms, setPaymentTerms] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Not a useEffect: React's own guidance for "adjust state when data
  // arrives" is to compare against the previous render's id during render
  // itself, not sync it in an effect (which would cause a needless extra
  // render pass before the form ever shows real data).
  const [loadedForId, setLoadedForId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["quotation", companyId, id],
    queryFn: () => salesApi.getQuotation(companyId, id),
  });
  const quotation = data?.quotation;
  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "customers"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { customersOnly: true }),
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

  if (data && loadedForId !== id) {
    setPartnerId(data.quotation.partner_id);
    setQuoteDate(data.quotation.quote_date);
    setTaxRateId(data.lines[0]?.tax_rate_id ?? "");
    setWarehouseId(data.quotation.warehouse_id ?? "");
    setPaymentTerms(data.quotation.payment_terms ?? "");
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
      salesApi.updateQuotation(companyId, branchId, id, {
        partner_id: partnerId,
        quote_date: quoteDate,
        warehouse_id: warehouseId || null,
        payment_terms: paymentTerms || null,
        lines: lines.map((l) => ({ ...l, tax_rate_id: effectiveTaxRateId })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quotation", companyId, id] });
      queryClient.invalidateQueries({ queryKey: ["quotations", companyId] });
      router.push(`/sales/quotations/${id}`);
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
  if (!quotation) return null;
  if (quotation.status !== "draft") {
    return (
      <div className="max-w-xl space-y-4">
        <Button variant="ghost" size="sm" onClick={() => router.push(`/sales/quotations/${id}`)}>
          <ArrowLeft className="h-4 w-4" />
          {t("common.back")}
        </Button>
        <p className="text-sm text-muted-foreground">{t("sales.quotations.edit_locked")}</p>
      </div>
    );
  }

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push(`/sales/quotations/${id}`)}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>
            {t("common.edit")} — {quotation.number}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>{t("sales.quotations.customer")}</Label>
            <Select value={partnerId} onValueChange={(v) => setPartnerId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("sales.quotations.select_customer")}>
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
            <Label>{t("sales.quotations.date")}</Label>
            <Input type="date" value={quoteDate} onChange={(e) => setQuoteDate(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>{t("inventory.stock.warehouse")}</Label>
            <Select value={warehouseId} onValueChange={(v) => setWarehouseId(v ?? "")}>
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
                  <Label className="text-xs">{t("sales.quotations.select_product")}</Label>
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
                        unit_price: product ? String(product.sales_price) : line.unit_price,
                      });
                    }}
                    placeholder={t("sales.quotations.select_product")}
                  />
                  <StockBalanceHint companyId={companyId} productId={line.product_id} warehouseId={warehouseId} />
                </div>
                <div className="w-20 space-y-1">
                  <Label className="text-xs">{t("sales.quotations.qty")}</Label>
                  <Input value={line.qty} onChange={(e) => updateLine(index, { qty: e.target.value })} />
                </div>
                <div className="w-24 space-y-1">
                  <Label className="text-xs">{t("sales.quotations.unit_price")}</Label>
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
              {t("sales.quotations.add_line")}
            </Button>
          </div>
          <div className="space-y-2">
            <Label>{t("sales.quotations.payment_terms")}</Label>
            <Textarea
              value={paymentTerms}
              onChange={(e) => setPaymentTerms(e.target.value)}
              placeholder={t("sales.quotations.payment_terms_placeholder")}
              rows={2}
            />
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
