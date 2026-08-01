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
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { salesApi } from "@/features/sales/api/client";
import { ApiError } from "@/lib/api-client";

// The nucleus doesn't expose a tax-rate list endpoint yet (Phase 1 §7's
// default Saudi VAT rates are seeded per company but only readable today
// via the accounting service layer, not a dedicated API) — the backend
// itself doesn't validate this FK (see Phase 7 §4 note on quotation_line),
// so a fixed Standard-15% placeholder is used here rather than blocking
// quotation creation on a lookup that doesn't exist yet.
const STANDARD_VAT_TAX_RATE_ID = "00000000-0000-0000-0000-000000000001";

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

  const createMutation = useMutation({
    mutationFn: () =>
      salesApi.createQuotation(companyId, branchId, {
        partner_id: partnerId,
        quote_date: quoteDate,
        lines: lines.map((l) => ({ ...l, tax_rate_id: STANDARD_VAT_TAX_RATE_ID })),
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
            <Select value={partnerId} onValueChange={(v) => setPartnerId(v ?? "")}>
              <SelectTrigger className="w-full">
                {/* Base UI's Select.Value shows the raw `value` (the UUID)
                    by default — it does not look up the matching SelectItem's
                    rendered children. A `children` render function is
                    required to display the label instead. */}
                <SelectValue placeholder={t("sales.quotations.select_customer")}>
                  {(value: string) => partnersQuery.data?.find((p) => p.id === value)?.name ?? value}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {partnersQuery.data?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
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
            {lines.map((line, index) => (
              <div key={index} className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  <Label className="text-xs">{t("sales.quotations.select_product")}</Label>
                  <Select value={line.product_id} onValueChange={(v) => updateLine(index, { product_id: v ?? "" })}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t("sales.quotations.select_product")}>
                        {(value: string) => productsQuery.data?.find((p) => p.id === value)?.name ?? value}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {productsQuery.data?.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
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
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!partnerId || createMutation.isPending}
          >
            {createMutation.isPending ? t("common.loading") : t("sales.quotations.save")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
