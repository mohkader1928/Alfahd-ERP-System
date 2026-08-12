"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { salesApi } from "@/features/sales/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";

export default function SalesOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;
  const [invoiceQtys, setInvoiceQtys] = useState<Record<string, string>>({});
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["sales-order", companyId, id],
    queryFn: () => salesApi.getSalesOrder(companyId, id),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["sales-order", companyId, id] });
    queryClient.invalidateQueries({ queryKey: ["sales-orders", companyId] });
  };

  function handleError(err: unknown) {
    const detail = err instanceof ApiError ? err.detail : t("common.error");
    setActionError(detail);
    toastError(t("toast.error_title"), detail);
  }

  const invoiceMutation = useMutation({
    mutationFn: () => {
      // Only send an explicit lines[] when the buyer actually trimmed a
      // quantity below the full remaining amount — omitting it entirely
      // keeps the original "invoice everything remaining" one-click
      // behavior working exactly as before.
      const trimmed = data!.lines
        .map((l) => {
          const remaining = Number(l.qty) - Number(l.qty_invoiced);
          const requested = invoiceQtys[l.id] !== undefined ? Number(invoiceQtys[l.id]) : remaining;
          const qty = Math.min(Math.max(requested, 0), remaining);
          return { sales_order_line_id: l.id, qty: String(qty) };
        })
        .filter((l) => Number(l.qty) > 0);
      const isFullInvoice = trimmed.length === data!.lines.length && data!.lines.every((l) => {
        const remaining = Number(l.qty) - Number(l.qty_invoiced);
        return Number(invoiceQtys[l.id] ?? remaining) >= remaining;
      });
      return salesApi.issueInvoice(companyId, branchId, id, isFullInvoice ? undefined : trimmed);
    },
    onSuccess: (result) => {
      invalidate();
      setInvoiceQtys({});
      toastSuccess(t("toast.success_title"), result.invoice.number);
      router.push(`/sales/invoices/${result.invoice.id}`);
    },
    onError: handleError,
  });

  const cancelMutation = useMutation({
    mutationFn: () => salesApi.cancelSalesOrder(companyId, id, cancelReason),
    onSuccess: () => {
      invalidate();
      setCancelOpen(false);
      setCancelReason("");
      toastSuccess(t("toast.success_title"), t("sales.orders.cancel"));
    },
    onError: handleError,
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;

  const { order, lines } = data;
  const productLabel = (productId: string) => productsQuery.data?.find((p) => p.id === productId)?.name ?? productId;
  const canInvoice = order.status === "confirmed" || order.status === "partially_invoiced";
  // Nothing invoiced yet on any line — the same precondition the backend
  // enforces for edit/cancel.
  const canEditOrCancel =
    (order.status === "draft" || order.status === "confirmed") &&
    lines.every((l) => Number(l.qty_invoiced) === 0);

  return (
    <div className="max-w-2xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/sales/orders")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            {order.number}
            <Badge variant={statusVariant(order.status)}>{t(`sales.orders.status_${order.status}`)}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("sales.orders.date")}</dt>
            <dd>{order.order_date}</dd>
            <dt className="text-muted-foreground">{t("sales.orders.total")}</dt>
            <dd>{formatCurrency(order.total_amount)}</dd>
          </dl>
          {order.status === "cancelled" && order.cancellation_reason && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {order.cancellation_reason}
            </p>
          )}
          {order.status === "partially_invoiced" && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-400">
              {t("sales.orders.insufficient_stock_hint")}
            </p>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("purchasing.orders.select_product")}</TableHead>
                <TableHead className="text-end">{t("sales.orders.qty_ordered")}</TableHead>
                <TableHead className="text-end">{t("sales.orders.qty_invoiced")}</TableHead>
                <TableHead className="text-end">{t("sales.orders.remaining")}</TableHead>
                {canInvoice && <TableHead className="text-end">{t("sales.orders.invoice_qty")}</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => {
                const remaining = Number(l.qty) - Number(l.qty_invoiced);
                return (
                  <TableRow key={l.id}>
                    <TableCell>{productLabel(l.product_id)}</TableCell>
                    <TableCell className="text-end">{l.qty}</TableCell>
                    <TableCell className="text-end">{l.qty_invoiced}</TableCell>
                    <TableCell className="text-end">{remaining > 0 ? remaining : "0"}</TableCell>
                    {canInvoice && (
                      <TableCell className="text-end">
                        {remaining > 0 ? (
                          <Input
                            className="w-24 text-end"
                            value={invoiceQtys[l.id] ?? String(remaining)}
                            onChange={(e) => setInvoiceQtys((prev) => ({ ...prev, [l.id]: e.target.value }))}
                          />
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <div className="flex flex-wrap gap-2">
            {canEditOrCancel && (
              <Can permission="sales.order.update">
                <Button variant="outline" onClick={() => router.push(`/sales/orders/${id}/edit`)}>
                  {t("common.edit")}
                </Button>
              </Can>
            )}
            {canInvoice && (
              <Can permission="sales.invoice.create">
                <Button onClick={() => invoiceMutation.mutate()} disabled={invoiceMutation.isPending}>
                  {invoiceMutation.isPending ? t("common.loading") : t("sales.orders.invoice")}
                </Button>
              </Can>
            )}
            {canEditOrCancel && (
              <Can permission="sales.order.cancel">
                <Button variant="outline" onClick={() => setCancelOpen(true)}>
                  {t("sales.orders.cancel")}
                </Button>
              </Can>
            )}
          </div>
          {actionError && <p className="text-sm text-destructive">{actionError}</p>}
        </CardContent>
      </Card>

      <Dialog open={cancelOpen} onOpenChange={(open) => !open && setCancelOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("sales.orders.cancel_dialog_title")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label>{t("sales.orders.cancel_reason")}</Label>
            <Textarea value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} rows={3} autoFocus />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={!cancelReason.trim() || cancelMutation.isPending}
              onClick={() => cancelMutation.mutate()}
            >
              {cancelMutation.isPending ? t("common.loading") : t("sales.orders.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
