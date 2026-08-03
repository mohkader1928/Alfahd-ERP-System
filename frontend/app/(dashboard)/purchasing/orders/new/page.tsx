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
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";

// Same nucleus gap as the sales quotation form: no tax-rate list endpoint
// yet, so a fixed Standard-15% placeholder is used (backend doesn't
// validate this FK — see sales/quotations/new/page.tsx for the full note).
const STANDARD_VAT_TAX_RATE_ID = "00000000-0000-0000-0000-000000000001";

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

  const createMutation = useMutation({
    mutationFn: () =>
      purchasingApi.createOrder(companyId, branchId, {
        partner_id: partnerId,
        order_date: orderDate,
        lines: lines.map((l) => ({ ...l, tax_rate_id: STANDARD_VAT_TAX_RATE_ID })),
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
            <Label>{t("purchasing.orders.date")}</Label>
            <Input type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
          </div>
          <div className="space-y-2">
            {lines.map((line, index) => (
              <div key={index} className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  <Label className="text-xs">{t("purchasing.orders.select_product")}</Label>
                  <Select value={line.product_id} onValueChange={(v) => updateLine(index, { product_id: v ?? "" })}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t("purchasing.orders.select_product")}>
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
            disabled={!partnerId || createMutation.isPending}
          >
            {createMutation.isPending ? t("common.loading") : t("purchasing.orders.save")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
