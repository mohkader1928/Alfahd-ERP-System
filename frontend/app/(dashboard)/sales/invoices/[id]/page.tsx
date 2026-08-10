"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "react-qr-code";
import { ArrowLeft } from "lucide-react";
import { Download, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Can } from "@/components/erp/permissions/can";
import { AttachmentsPanel } from "@/components/erp/attachments/attachments-panel";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { salesApi } from "@/features/sales/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";

export default function InvoiceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, locale } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(true);
  const [emailDialogOpen, setEmailDialogOpen] = useState(false);
  const [emailOverride, setEmailOverride] = useState("");
  const [downloading, setDownloading] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["invoice", companyId, id],
    queryFn: () => salesApi.getInvoice(companyId, id),
  });

  const creditNoteMutation = useMutation({
    mutationFn: () => salesApi.issueCreditNote(companyId, branchId, id, reason, restock),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["invoice", companyId, id] });
      toastSuccess(t("toast.success_title"), result.invoice.number);
      router.push(`/sales/invoices/${result.invoice.id}`);
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  async function handleDownloadPdf() {
    setDownloading(true);
    try {
      const { blob, filename } = await salesApi.downloadInvoicePdf(companyId, id, locale);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `${data?.invoice.number ?? "invoice"}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error"));
    } finally {
      setDownloading(false);
    }
  }

  const sendEmailMutation = useMutation({
    mutationFn: () => salesApi.sendInvoiceEmail(companyId, id, emailOverride.trim() || undefined),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["invoice", companyId, id] });
      setEmailDialogOpen(false);
      setEmailOverride("");
      toastSuccess(t("toast.success_title"), `${t("sales.invoice.email_sent")} ${updated.last_emailed_to ?? ""}`);
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  if (isLoading) return <Skeleton className="h-60 w-full" />;
  if (!data) return null;

  const { invoice, zatca_submission } = data;

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/sales/invoices")}>
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
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={handleDownloadPdf} disabled={downloading}>
              <Download className="h-4 w-4" />
              {downloading ? t("common.loading") : t("sales.invoice.download_pdf")}
            </Button>
            <Can permission="sales.invoice.send_email">
              <Button variant="outline" size="sm" onClick={() => setEmailDialogOpen(true)}>
                <Mail className="h-4 w-4" />
                {t("sales.invoice.send_email")}
              </Button>
            </Can>
          </div>
          {invoice.last_emailed_at && (
            <p className="text-xs text-muted-foreground">
              {t("sales.invoice.last_emailed")} {formatDate(invoice.last_emailed_at, locale)}
              {invoice.last_emailed_to ? ` (${invoice.last_emailed_to})` : ""}
            </p>
          )}
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">Type</dt>
            <dd className="capitalize">{invoice.invoice_type.replace("_", " ")}</dd>
            <dt className="text-muted-foreground">{t("sales.invoice.date")}</dt>
            <dd>{formatDate(invoice.invoice_date, locale)}</dd>
            {invoice.sales_order_id && (
              <>
                <dt className="text-muted-foreground">{t("sales.invoice.from_order")}</dt>
                <dd>
                  <a
                    href={`/sales/orders/${invoice.sales_order_id}`}
                    onClick={(e) => {
                      e.preventDefault();
                      router.push(`/sales/orders/${invoice.sales_order_id}`);
                    }}
                    className="underline-offset-4 hover:underline"
                  >
                    {t("common.view")}
                  </a>
                </dd>
              </>
            )}
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
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={restock} onChange={(e) => setRestock(e.target.checked)} />
                  {t("sales.invoice.restock_label")}
                </label>
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

          <AttachmentsPanel entityType="sales_invoice" entityId={invoice.id} />
        </CardContent>
      </Card>

      <Dialog open={emailDialogOpen} onOpenChange={(open) => !open && setEmailDialogOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("sales.invoice.send_email")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label>{t("sales.invoice.recipient_email")}</Label>
            <Input
              type="email"
              placeholder={t("sales.invoice.recipient_email_placeholder")}
              value={emailOverride}
              onChange={(e) => setEmailOverride(e.target.value)}
              autoFocus
            />
          </div>
          {sendEmailMutation.isError && (
            <p className="text-sm text-destructive">
              {sendEmailMutation.error instanceof ApiError ? sendEmailMutation.error.detail : t("common.error")}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmailDialogOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => sendEmailMutation.mutate()} disabled={sendEmailMutation.isPending}>
              {sendEmailMutation.isPending ? t("common.loading") : t("sales.invoice.send_email")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
