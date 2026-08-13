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
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import { identityApi } from "@/features/identity/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";

interface Line {
  product_id: string;
  qty: string;
  unit_price: string;
}

// Product Owner request: a Purchase Return is not necessarily for one
// whole vendor bill — it's a freeform set of lines (possibly spanning
// several bills, or none at all), with the original bill reduced to an
// OPTIONAL traceability field. Same line-editor pattern as
// purchasing/orders/new; the vendor must be picked directly since there
// may be no bill to infer it from.
export default function NewPurchaseReturnPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [originalBillId, setOriginalBillId] = useState("");
  const [taxRateId, setTaxRateId] = useState("");
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(true);
  const [lines, setLines] = useState<Line[]>([{ product_id: "", qty: "1", unit_price: "0" }]);
  const [error, setError] = useState<string | null>(null);

  const vendorsQuery = useQuery({
    queryKey: ["partners", companyId, "vendor"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  // Only a posted, standard bill can be referenced (the service rejects
  // anything else) — this field is optional, purely for traceability.
  const billsQuery = useQuery({
    queryKey: ["vendor-bills", companyId, "returnable"],
    queryFn: () => purchasingApi.listVendorBills(companyId, { pageSize: 200 }),
  });
  const referenceableBills = (billsQuery.data?.items ?? []).filter(
    (bill) =>
      bill.bill_type === "standard" && bill.status === "posted" && (!partnerId || bill.partner_id === partnerId)
  );
  const taxRatesQuery = useQuery({
    queryKey: ["tax-rates", companyId],
    queryFn: () => accountingApi.listTaxRates(companyId),
  });
  const effectiveTaxRateId =
    taxRateId || taxRatesQuery.data?.find((r) => r.kind === "standard")?.id || "";

  const createMutation = useMutation({
    mutationFn: () =>
      purchasingApi.issueDebitNoteForLines(companyId, branchId, {
        partner_id: partnerId,
        original_bill_id: originalBillId || undefined,
        reason,
        restock,
        lines: lines.map((l) => ({ ...l, tax_rate_id: effectiveTaxRateId })),
      }),
    onSuccess: (bill) => {
      queryClient.invalidateQueries({ queryKey: ["purchase-returns", companyId] });
      queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] });
      router.push(`/purchasing/bills/${bill.id}`);
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

  const canSubmit =
    !!partnerId &&
    !!effectiveTaxRateId &&
    !!reason &&
    lines.every((l) => l.product_id && Number(l.qty) > 0) &&
    !createMutation.isPending;

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/purchasing/returns")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{t("purchasing.returns.new")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>{t("purchasing.orders.vendor")}</Label>
            <Select
              value={partnerId}
              onValueChange={(v) => {
                setPartnerId(v ?? "");
                setOriginalBillId("");
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("purchasing.orders.select_vendor")}>
                  {(value: string) => {
                    const partner = vendorsQuery.data?.find((p) => p.id === value);
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
                {vendorsQuery.data?.map((p) => (
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
            <Label>
              {t("purchasing.returns.select_bill")}{" "}
              <span className="text-xs text-muted-foreground">({t("common.optional")})</span>
            </Label>
            <Select value={originalBillId} onValueChange={(v) => setOriginalBillId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("purchasing.returns.select_bill")}>
                  {(value: string) => {
                    const bill = referenceableBills.find((b) => b.id === value);
                    return bill ? `${bill.number} — ${formatCurrency(bill.total_amount)}` : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {referenceableBills.map((bill) => (
                  <SelectItem key={bill.id} value={bill.id}>
                    {bill.number} — {formatCurrency(bill.total_amount)}
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

          <div className="space-y-2">
            <Label>{t("purchasing.returns.reason")}</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("purchasing.returns.reason")} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={restock} onChange={(e) => setRestock(e.target.checked)} />
            {t("purchasing.vendor_bills.restock_label")}
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!canSubmit}
          >
            {createMutation.isPending ? t("common.loading") : t("purchasing.returns.new")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
