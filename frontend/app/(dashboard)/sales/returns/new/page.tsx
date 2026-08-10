"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
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
import { formatCurrency } from "@/lib/format-currency";

export default function NewSalesReturnPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [invoiceId, setInvoiceId] = useState("");
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Only a tax/simplified invoice can be returned (the service rejects
  // anything else) — credit notes and debit-type documents are excluded
  // client-side so the picker only ever offers a valid original document.
  const invoicesQuery = useQuery({
    queryKey: ["sales-invoices", companyId, "returnable"],
    queryFn: () => salesApi.listInvoices(companyId, { pageSize: 200 }),
  });
  const returnableInvoices = (invoicesQuery.data?.items ?? []).filter(
    (inv) => inv.invoice_type === "tax" || inv.invoice_type === "simplified"
  );

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "customer"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { customersOnly: true }),
  });
  const customerLabel = (partnerId: string) =>
    partnersQuery.data?.find((p) => p.id === partnerId)?.name ?? partnerId;

  const createMutation = useMutation({
    mutationFn: () => salesApi.issueCreditNote(companyId, branchId, invoiceId, reason, restock),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["sales-returns", companyId] });
      queryClient.invalidateQueries({ queryKey: ["sales-invoices", companyId] });
      router.push(`/sales/invoices/${result.invoice.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

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
            <Label>{t("sales.returns.select_invoice")}</Label>
            <Select value={invoiceId} onValueChange={(v) => setInvoiceId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("sales.returns.select_invoice")}>
                  {(value: string) => {
                    const invoice = returnableInvoices.find((i) => i.id === value);
                    return invoice ? `${invoice.number} — ${customerLabel(invoice.partner_id)}` : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {returnableInvoices.map((invoice) => (
                  <SelectItem key={invoice.id} value={invoice.id}>
                    {invoice.number} — {customerLabel(invoice.partner_id)} — {formatCurrency(invoice.total_amount)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
            disabled={!invoiceId || !reason || createMutation.isPending}
          >
            {createMutation.isPending ? t("common.loading") : t("sales.returns.new")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
