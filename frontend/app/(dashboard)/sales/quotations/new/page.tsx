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

// This is a full page rather than a modal Dialog deliberately: a Dialog
// hosting multiple Select dropdowns hit a real nested-overlay conflict in
// this stack (Base UI's Select defaults to `modal: true`, and closing it
// after picking an option was closing the parent Dialog too, not just
// applying the selection). A dedicated route sidesteps the conflict
// entirely rather than fighting library internals, and is arguably better
// UX for a multi-line form regardless.
export default function NewQuotationPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [quoteDate, setQuoteDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [taxRateId, setTaxRateId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [costCenterId, setCostCenterId] = useState("");
  const [lines, setLines] = useState<Line[]>([{ product_id: "", qty: "1", unit_price: "0" }]);
  const [paymentTerms, setPaymentTerms] = useState("");
  const [paymentTermsTouched, setPaymentTermsTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
  const costCentersQuery = useQuery({
    queryKey: ["cost-centers", companyId],
    queryFn: () => accountingApi.listCostCenters(companyId),
  });
  // Defaults to the company's own configured Standard rate once loaded,
  // without a separate effect — the user can still override it below.
  const effectiveTaxRateId =
    taxRateId || taxRatesQuery.data?.find((r) => r.kind === "standard")?.id || "";
  // Same pattern for warehouse: defaults to the company's default
  // warehouse once loaded, but a company with none configured (a
  // service-only business) simply has no warehouse field to fill —
  // stock balance hints and the eventual stock deduction just stay off.
  const effectiveWarehouseId =
    warehouseId || warehousesQuery.data?.find((w) => w.is_default)?.id || "";

  const createMutation = useMutation({
    mutationFn: () =>
      salesApi.createQuotation(companyId, branchId, {
        partner_id: partnerId,
        quote_date: quoteDate,
        warehouse_id: effectiveWarehouseId || null,
        cost_center_id: costCenterId || null,
        payment_terms: paymentTerms || null,
        lines: lines.map((l) => ({ ...l, tax_rate_id: effectiveTaxRateId })),
      }),
    onSuccess: (quotation) => {
      queryClient.invalidateQueries({ queryKey: ["quotations", companyId] });
      router.push(`/sales/quotations/${quotation.id}`);
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

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/sales/quotations")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{t("sales.quotations.create_title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>{t("sales.quotations.customer")}</Label>
            <Select
              value={partnerId}
              onValueChange={(v) => {
                setPartnerId(v ?? "");
                // Owner request: default the quotation's payment terms
                // from the customer's own record, but only while the user
                // hasn't already typed something here themselves — never
                // clobber a manual edit by switching customers.
                if (!paymentTermsTouched) {
                  const partner = partnersQuery.data?.find((p) => p.id === v);
                  setPaymentTerms(partner?.payment_terms ?? "");
                }
              }}
            >
              <SelectTrigger className="w-full">
                {/* Base UI's Select.Value shows the raw `value` (the UUID)
                    by default — it does not look up the matching SelectItem's
                    rendered children. A `children` render function is
                    required to display the label instead. */}
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
            <Label>{t("accounting.gl.cost_center")}</Label>
            <Select value={costCenterId} onValueChange={(v) => setCostCenterId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("sales.cost_center_none")}>
                  {(value: string) => {
                    if (!value) return t("sales.cost_center_none");
                    return costCentersQuery.data?.find((c) => c.id === value)?.name ?? value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">{t("sales.cost_center_none")}</SelectItem>
                {costCentersQuery.data?.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
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
                      // Owner-requested default: picking a product pre-fills
                      // the line price from the product master's sales_price
                      // instead of leaving the salesperson typing "0" from
                      // scratch on every line.
                      updateLine(index, {
                        product_id: v ?? "",
                        unit_price: product ? String(product.sales_price) : line.unit_price,
                      });
                    }}
                    placeholder={t("sales.quotations.select_product")}
                  />
                  <StockBalanceHint
                    companyId={companyId}
                    productId={line.product_id}
                    warehouseId={effectiveWarehouseId}
                  />
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
              onChange={(e) => {
                setPaymentTerms(e.target.value);
                setPaymentTermsTouched(true);
              }}
              placeholder={t("sales.quotations.payment_terms_placeholder")}
              rows={2}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!partnerId || !effectiveTaxRateId || createMutation.isPending}
          >
            {createMutation.isPending ? t("common.loading") : t("sales.quotations.save")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
