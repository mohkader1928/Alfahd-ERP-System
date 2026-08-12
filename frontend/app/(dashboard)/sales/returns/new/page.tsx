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
import { identityApi } from "@/features/identity/api/client";
import { salesApi } from "@/features/sales/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";

// The nucleus doesn't expose a tax-rate list endpoint yet — same
// placeholder every other freeform line editor in this codebase uses
// (see sales/quotations/new).
const STANDARD_VAT_TAX_RATE_ID = "00000000-0000-0000-0000-000000000001";

interface Line {
  product_id: string;
  qty: string;
  unit_price: string;
}

// Product Owner request: a Sales Return is not necessarily for one whole
// invoice — it's a freeform set of lines (possibly spanning several
// invoices, or none at all), with the original invoice reduced to an
// OPTIONAL traceability field. Same line-editor pattern as
// sales/quotations/new; the customer must be picked directly since there
// may be no invoice to infer it from.
export default function NewSalesReturnPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [originalInvoiceId, setOriginalInvoiceId] = useState("");
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(true);
  const [lines, setLines] = useState<Line[]>([{ product_id: "", qty: "1", unit_price: "0" }]);
  const [error, setError] = useState<string | null>(null);

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "customers"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { customersOnly: true }),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  // Only a tax/simplified invoice can be referenced (the service rejects
  // anything else) — this field is optional, purely for traceability.
  const invoicesQuery = useQuery({
    queryKey: ["sales-invoices", companyId, "returnable"],
    queryFn: () => salesApi.listInvoices(companyId, { pageSize: 200 }),
  });
  const referenceableInvoices = (invoicesQuery.data?.items ?? []).filter(
    (inv) =>
      (inv.invoice_type === "tax" || inv.invoice_type === "simplified") &&
      (!partnerId || inv.partner_id === partnerId)
  );

  const createMutation = useMutation({
    mutationFn: () =>
      salesApi.issueCreditNoteForLines(companyId, branchId, {
        partner_id: partnerId,
        original_invoice_id: originalInvoiceId || undefined,
        reason,
        restock,
        lines: lines.map((l) => ({ ...l, tax_rate_id: STANDARD_VAT_TAX_RATE_ID })),
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["sales-returns", companyId] });
      queryClient.invalidateQueries({ queryKey: ["sales-invoices", companyId] });
      router.push(`/sales/invoices/${result.invoice.id}`);
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
    !!partnerId && !!reason && lines.every((l) => l.product_id && Number(l.qty) > 0) && !createMutation.isPending;

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/sales/returns")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{t("sales.returns.new")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>{t("sales.quotations.customer")}</Label>
            <Select
              value={partnerId}
              onValueChange={(v) => {
                setPartnerId(v ?? "");
                setOriginalInvoiceId("");
              }}
            >
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
            <Label>
              {t("sales.returns.select_invoice")}{" "}
              <span className="text-xs text-muted-foreground">({t("common.optional")})</span>
            </Label>
            <Select value={originalInvoiceId} onValueChange={(v) => setOriginalInvoiceId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("sales.returns.select_invoice")}>
                  {(value: string) => {
                    const invoice = referenceableInvoices.find((i) => i.id === value);
                    return invoice ? `${invoice.number} — ${formatCurrency(invoice.total_amount)}` : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {referenceableInvoices.map((invoice) => (
                  <SelectItem key={invoice.id} value={invoice.id}>
                    {invoice.number} — {formatCurrency(invoice.total_amount)}
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
            <Label>{t("sales.returns.reason")}</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("sales.returns.reason")} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={restock} onChange={(e) => setRestock(e.target.checked)} />
            {t("sales.invoice.restock_label")}
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!canSubmit}
          >
            {createMutation.isPending ? t("common.loading") : t("sales.returns.new")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
