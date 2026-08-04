"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "react-qr-code";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { salesApi } from "@/features/sales/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";

export default function InvoiceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;
  const [reason, setReason] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["invoice", companyId, id],
    queryFn: () => salesApi.getInvoice(companyId, id),
  });

  const creditNoteMutation = useMutation({
    mutationFn: () => salesApi.issueCreditNote(companyId, branchId, id, reason),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["invoice", companyId, id] });
      toastSuccess(t("toast.success_title"), result.invoice.number);
      router.push(`/sales/invoices/${result.invoice.id}`);
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  if (isLoading) return <Skeleton className="h-60 w-full" />;
  if (!data) return null;

  const { invoice, zatca_submission } = data;

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/sales/quotations")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            {t("sales.invoice.title")} — {invoice.number}
            <Badge variant={statusVariant(invoice.status)}>{invoice.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">Type</dt>
            <dd className="capitalize">{invoice.invoice_type.replace("_", " ")}</dd>
            <dt className="text-muted-foreground">Subtotal</dt>
            <dd>{formatCurrency(invoice.subtotal_amount)}</dd>
            <dt className="text-muted-foreground">VAT</dt>
            <dd>{formatCurrency(invoice.tax_amount)}</dd>
            <dt className="text-muted-foreground">{t("sales.quotations.total")}</dt>
            <dd className="font-semibold">{formatCurrency(invoice.total_amount)}</dd>
          </dl>

          <div className="space-y-2 border-t pt-4">
            <p className="text-sm font-medium">{t("sales.invoice.zatca_qr")}</p>
            <div className="flex justify-center rounded-md border bg-white p-4">
              <QRCode value={zatca_submission.qr_payload} size={160} />
            </div>
            <p className="text-center text-xs text-muted-foreground">
              {zatca_submission.submission_mode === "clearance" ? "Clearance" : "Reporting"} · ICV{" "}
              {zatca_submission.icv}
            </p>
          </div>

          {invoice.invoice_type !== "credit_note" && invoice.invoice_type !== "debit_note" && (
            <Can permission="sales.invoice.credit_note">
              <div className="space-y-2 border-t pt-4">
                <Input
                  placeholder="Reason for credit note"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <Button
                  variant="outline"
                  onClick={() => creditNoteMutation.mutate()}
                  disabled={!reason || creditNoteMutation.isPending}
                >
                  {creditNoteMutation.isPending ? t("common.loading") : t("sales.invoice.credit_note")}
                </Button>
                {creditNoteMutation.isError && (
                  <p className="text-sm text-destructive">
                    {creditNoteMutation.error instanceof ApiError ? creditNoteMutation.error.detail : t("common.error")}
                  </p>
                )}
              </div>
            </Can>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
