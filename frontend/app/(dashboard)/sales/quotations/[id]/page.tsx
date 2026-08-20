"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { salesApi } from "@/features/sales/api/client";
import { ApiError, friendlyApiErrorMessage } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";

export default function QuotationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, locale } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;
  const [emailDialogOpen, setEmailDialogOpen] = useState(false);
  const [emailOverride, setEmailOverride] = useState("");
  const [downloading, setDownloading] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["quotation", companyId, id],
    queryFn: () => salesApi.getQuotation(companyId, id),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });

  const confirmMutation = useMutation({
    mutationFn: () => salesApi.confirmQuotation(companyId, branchId, id),
    onSuccess: (order) => {
      queryClient.invalidateQueries({ queryKey: ["quotations", companyId] });
      toastSuccess(t("toast.success_title"), order.number);
      router.push(`/sales/orders/${order.id}`);
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  async function handleDownloadPdf() {
    setDownloading(true);
    try {
      const { blob, filename } = await salesApi.downloadQuotationPdf(companyId, id, locale);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `${data?.quotation.number ?? "quotation"}.pdf`;
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
    mutationFn: () => salesApi.sendQuotationEmail(companyId, id, emailOverride.trim() || undefined),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["quotation", companyId, id] });
      setEmailDialogOpen(false);
      setEmailOverride("");
      toastSuccess(t("toast.success_title"), `${t("sales.quotations.email_sent")} ${updated.last_emailed_to ?? ""}`);
    },
    onError: (err) => toastError(t("toast.error_title"), friendlyApiErrorMessage(err, t)),
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;
  const { quotation, lines } = data;
  const productOf = (productId: string) => productsQuery.data?.find((p) => p.id === productId);

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/sales/quotations")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            {quotation.number}
            <Badge variant={statusVariant(quotation.status)}>{quotation.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={handleDownloadPdf} disabled={downloading}>
              <Download className="h-4 w-4" />
              {downloading ? t("common.loading") : t("sales.quotations.download_pdf")}
            </Button>
            <Can permission="sales.quotation.send_email">
              <Button variant="outline" size="sm" onClick={() => setEmailDialogOpen(true)}>
                <Mail className="h-4 w-4" />
                {t("sales.quotations.send_email")}
              </Button>
            </Can>
          </div>
          {quotation.last_emailed_at && (
            <p className="text-xs text-muted-foreground">
              {t("sales.quotations.last_emailed")} {formatDate(quotation.last_emailed_at, locale)}
              {quotation.last_emailed_to ? ` (${quotation.last_emailed_to})` : ""}
            </p>
          )}
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("sales.quotations.date")}</dt>
            <dd>{quotation.quote_date}</dd>
            <dt className="text-muted-foreground">{t("inventory.stock.warehouse")}</dt>
            <dd>
              {warehousesQuery.data?.find((w) => w.id === quotation.warehouse_id)?.name ??
                quotation.warehouse_id ??
                "—"}
            </dd>
            <dt className="text-muted-foreground">{t("sales.quotations.total")}</dt>
            <dd>{formatCurrency(quotation.total_amount)}</dd>
          </dl>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("sales.quotations.select_product")}</TableHead>
                <TableHead className="text-end">{t("sales.quotations.qty")}</TableHead>
                <TableHead className="text-end">{t("sales.quotations.unit_price")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => {
                const product = productOf(l.product_id);
                return (
                  <TableRow key={l.id}>
                    <TableCell>
                      <span className="flex items-center gap-2">
                        <EntityImage src={product?.image_path} name={product?.name ?? l.product_id} size="xs" />
                        {product?.name ?? l.product_id}
                      </span>
                    </TableCell>
                    <TableCell className="text-end">{l.qty}</TableCell>
                    <TableCell className="text-end">{formatCurrency(l.unit_price)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {quotation.payment_terms && (
            <div className="space-y-1 border-t pt-3">
              <p className="text-xs text-muted-foreground">{t("sales.quotations.payment_terms")}</p>
              <p className="text-sm whitespace-pre-wrap">{quotation.payment_terms}</p>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {quotation.status === "draft" && (
              <Can permission="sales.quotation.update">
                <Button variant="outline" onClick={() => router.push(`/sales/quotations/${id}/edit`)}>
                  {t("common.edit")}
                </Button>
              </Can>
            )}
            {quotation.status === "draft" && (
              <Can permission="sales.quotation.confirm">
                <Button onClick={() => confirmMutation.mutate()} disabled={confirmMutation.isPending}>
                  {confirmMutation.isPending ? t("common.loading") : t("sales.quotations.confirm")}
                </Button>
              </Can>
            )}
          </div>
          {confirmMutation.isError && (
            <p className="text-sm text-destructive">
              {confirmMutation.error instanceof ApiError ? confirmMutation.error.detail : t("common.error")}
            </p>
          )}
        </CardContent>
      </Card>

      <Dialog open={emailDialogOpen} onOpenChange={(open) => !open && setEmailDialogOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("sales.quotations.send_email")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label>{t("sales.quotations.recipient_email")}</Label>
            <Input
              type="email"
              placeholder={t("sales.quotations.recipient_email_placeholder")}
              value={emailOverride}
              onChange={(e) => setEmailOverride(e.target.value)}
              autoFocus
            />
          </div>
          {sendEmailMutation.isError && (
            <p className="text-sm text-destructive">{friendlyApiErrorMessage(sendEmailMutation.error, t)}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmailDialogOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => sendEmailMutation.mutate()} disabled={sendEmailMutation.isPending}>
              {sendEmailMutation.isPending ? t("common.loading") : t("sales.quotations.send_email")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
