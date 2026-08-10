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
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";

export default function NewPurchaseReturnPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [billId, setBillId] = useState("");
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Only a posted, standard bill can be debit-noted (the service rejects
  // anything else) — debit notes themselves are excluded client-side so
  // the picker only ever offers a valid original document.
  const billsQuery = useQuery({
    queryKey: ["vendor-bills", companyId, "returnable"],
    queryFn: () => purchasingApi.listVendorBills(companyId, { pageSize: 200 }),
  });
  const returnableBills = (billsQuery.data?.items ?? []).filter(
    (bill) => bill.bill_type === "standard" && bill.status === "posted"
  );

  const vendorsQuery = useQuery({
    queryKey: ["partners", companyId, "vendor"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });
  const vendorLabel = (partnerId: string) =>
    vendorsQuery.data?.find((p) => p.id === partnerId)?.name ?? partnerId;

  const createMutation = useMutation({
    mutationFn: () => purchasingApi.issueDebitNote(companyId, branchId, billId, reason, restock),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["purchase-returns", companyId] });
      queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] });
      router.push(`/purchasing/bills/${result.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

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
            <Label>{t("purchasing.returns.select_bill")}</Label>
            <Select value={billId} onValueChange={(v) => setBillId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("purchasing.returns.select_bill")}>
                  {(value: string) => {
                    const bill = returnableBills.find((b) => b.id === value);
                    return bill ? `${bill.number} — ${vendorLabel(bill.partner_id)}` : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {returnableBills.map((bill) => (
                  <SelectItem key={bill.id} value={bill.id}>
                    {bill.number} — {vendorLabel(bill.partner_id)} — {formatCurrency(bill.total_amount)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
            disabled={!billId || !reason || createMutation.isPending}
          >
            {createMutation.isPending ? t("common.loading") : t("purchasing.returns.new")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
