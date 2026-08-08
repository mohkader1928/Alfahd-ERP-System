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
import { AttachmentsPanel } from "@/components/erp/attachments/attachments-panel";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";

export default function PurchaseOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;
  const [actionError, setActionError] = useState<string | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [receiveQtys, setReceiveQtys] = useState<Record<string, string>>({});
  const [remainingPromptOpen, setRemainingPromptOpen] = useState(false);
  const [shortCloseReason, setShortCloseReason] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["purchase-order", companyId, id],
    queryFn: () => purchasingApi.getOrder(companyId, id),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["purchase-order", companyId, id] });
    queryClient.invalidateQueries({ queryKey: ["purchase-orders", companyId] });
    queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] });
  };

  function handleError(err: unknown) {
    const detail = err instanceof ApiError ? err.detail : t("common.error");
    setActionError(detail);
    toastError(t("toast.error_title"), detail);
  }

  const confirmMutation = useMutation({
    mutationFn: () => purchasingApi.confirmOrder(companyId, id),
    onSuccess: (updated) => {
      invalidate();
      toastSuccess(
        t("toast.success_title"),
        updated.status === "pending_approval" ? t("purchasing.orders.sent_for_approval") : t("purchasing.orders.confirm")
      );
    },
    onError: handleError,
  });

  const approveMutation = useMutation({
    mutationFn: () => purchasingApi.approveOrder(companyId, id),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("purchasing.orders.approve"));
    },
    onError: handleError,
  });

  const rejectMutation = useMutation({
    mutationFn: () => purchasingApi.rejectOrder(companyId, id, rejectReason),
    onSuccess: () => {
      invalidate();
      setRejectOpen(false);
      setRejectReason("");
      toastSuccess(t("toast.success_title"), t("purchasing.orders.reject"));
    },
    onError: handleError,
  });

  const receiveMutation = useMutation({
    mutationFn: async () => {
      let stillRemaining = false;
      const toReceive = data!.lines
        .map((l) => {
          const remaining = Number(l.qty) - Number(l.qty_received);
          const requested = receiveQtys[l.id] !== undefined ? Number(receiveQtys[l.id]) : remaining;
          const qty = Math.min(Math.max(requested, 0), remaining);
          if (remaining - qty > 0) stillRemaining = true;
          return { purchase_order_line_id: l.id, qty: String(qty) };
        })
        .filter((l) => Number(l.qty) > 0);
      const receipt = await purchasingApi.recordGoodsReceipt(companyId, branchId, id, { lines: toReceive });
      return { receipt, stillRemaining };
    },
    onSuccess: ({ stillRemaining }) => {
      invalidate();
      setReceiveQtys({});
      toastSuccess(t("toast.success_title"), t("purchasing.orders.receive_submitted"));
      // P0-1: after a partial receipt, ask right away whether the rest
      // will be received later or should be short-closed now, instead of
      // leaving the PO open indefinitely with no clear next step.
      if (stillRemaining) setRemainingPromptOpen(true);
    },
    onError: handleError,
  });

  const shortCloseMutation = useMutation({
    mutationFn: () => purchasingApi.shortCloseOrder(companyId, id, shortCloseReason),
    onSuccess: () => {
      invalidate();
      setRemainingPromptOpen(false);
      setShortCloseReason("");
      toastSuccess(t("toast.success_title"), t("purchasing.orders.short_close"));
    },
    onError: handleError,
  });

  const reopenMutation = useMutation({
    mutationFn: (lineId: string) => purchasingApi.reopenOrderLine(companyId, id, lineId),
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("purchasing.orders.reopen_line"));
    },
    onError: handleError,
  });

  const billMutation = useMutation({
    mutationFn: () => {
      const receivedUnbilled = data!.lines
        .map((l) => ({
          purchase_order_line_id: l.id,
          qty: String(Number(l.qty_received) - Number(l.qty_billed)),
          unit_price: l.unit_price,
        }))
        .filter((l) => Number(l.qty) > 0);
      return purchasingApi.registerVendorBill(companyId, branchId, id, { lines: receivedUnbilled });
    },
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("purchasing.orders.bill_all"));
    },
    onError: handleError,
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;

  const { order, lines } = data;
  const productLabel = (productId: string) => productsQuery.data?.find((p) => p.id === productId)?.name ?? productId;
  const hasRemainingToReceive = lines.some((l) => Number(l.qty_received) < Number(l.qty) && !l.short_closed);
  const hasReceivedUnbilled = lines.some((l) => Number(l.qty_billed) < Number(l.qty_received));
  const remainingFor = (l: (typeof lines)[number]) => Number(l.qty) - Number(l.qty_received);
  // Owner-requested: the order's status now honestly reflects its data
  // (confirmed -> partially_received -> done/closed), so anywhere the
  // old code only checked for "confirmed" must also accept
  // "partially_received" -- both are "still receivable" states.
  const canReceive = order.status === "confirmed" || order.status === "partially_received";

  return (
    <div className="max-w-2xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/purchasing")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            {order.number}
            <Badge variant={statusVariant(order.status)} className="h-auto px-3 py-1 text-sm">
              {t(`purchasing.orders.status_${order.status}`)}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("purchasing.orders.date")}</dt>
            <dd>{order.order_date}</dd>
            <dt className="text-muted-foreground">{t("purchasing.orders.total")}</dt>
            <dd>{formatCurrency(order.total_amount)}</dd>
          </dl>
          {order.status === "pending_approval" && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-400">
              {t("purchasing.orders.pending_approval_notice")}
            </p>
          )}
          {order.approval_status === "rejected" && order.rejection_reason && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {t("purchasing.orders.rejected_notice")} {order.rejection_reason}
            </p>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("purchasing.orders.select_product")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.qty")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.received")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.remaining")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.billed")}</TableHead>
                {canReceive && hasRemainingToReceive && (
                  <TableHead className="text-end">{t("purchasing.orders.receive_qty")}</TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => {
                const remaining = remainingFor(l);
                return (
                <TableRow key={l.id}>
                  <TableCell>
                    {productLabel(l.product_id)}
                    {l.short_closed && (
                      <div className="mt-1 flex items-center gap-2">
                        <Badge variant="secondary">{t("purchasing.orders.short_closed")}</Badge>
                        <Can permission="purchasing.order.reopen">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-xs"
                            onClick={() => reopenMutation.mutate(l.id)}
                            disabled={reopenMutation.isPending}
                          >
                            {t("purchasing.orders.reopen_line")}
                          </Button>
                        </Can>
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-end">{l.qty}</TableCell>
                  <TableCell className="text-end">{l.qty_received}</TableCell>
                  <TableCell className="text-end">{remaining > 0 ? remaining : "0"}</TableCell>
                  <TableCell className="text-end">{l.qty_billed}</TableCell>
                  {canReceive && hasRemainingToReceive && (
                    <TableCell className="text-end">
                      {remaining > 0 && !l.short_closed ? (
                        <Input
                          className="w-20 text-end"
                          value={receiveQtys[l.id] ?? String(remaining)}
                          onChange={(e) => setReceiveQtys((prev) => ({ ...prev, [l.id]: e.target.value }))}
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
            {order.status === "draft" && (
              <Can permission="purchasing.order.confirm">
                <Button onClick={() => confirmMutation.mutate()} disabled={confirmMutation.isPending}>
                  {confirmMutation.isPending ? t("common.loading") : t("purchasing.orders.confirm")}
                </Button>
              </Can>
            )}
            {canReceive && hasRemainingToReceive && (
              <Can permission="purchasing.goods_receipt.create">
                <Button onClick={() => receiveMutation.mutate()} disabled={receiveMutation.isPending}>
                  {receiveMutation.isPending ? t("common.loading") : t("purchasing.orders.receive")}
                </Button>
              </Can>
            )}
            {canReceive && hasReceivedUnbilled && (
              <Can permission="purchasing.vendor_bill.create">
                <Button
                  variant="outline"
                  onClick={() => billMutation.mutate()}
                  disabled={billMutation.isPending}
                >
                  {billMutation.isPending ? t("common.loading") : t("purchasing.orders.bill_all")}
                </Button>
              </Can>
            )}
            {canReceive && hasRemainingToReceive && (
              <Can permission="purchasing.order.short_close">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShortCloseReason("");
                    setRemainingPromptOpen(true);
                  }}
                >
                  {t("purchasing.orders.close_remaining")}
                </Button>
              </Can>
            )}
            {order.status === "pending_approval" && (
              <Can permission="purchasing.order.approve">
                <Button onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
                  {approveMutation.isPending ? t("common.loading") : t("purchasing.orders.approve")}
                </Button>
                <Button variant="outline" onClick={() => setRejectOpen(true)}>
                  {t("purchasing.orders.reject")}
                </Button>
              </Can>
            )}
          </div>
          {actionError && <p className="text-sm text-destructive">{actionError}</p>}

          <AttachmentsPanel entityType="purchase_order" entityId={order.id} />
        </CardContent>
      </Card>

      <Dialog open={rejectOpen} onOpenChange={(open) => !open && setRejectOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("purchasing.orders.reject_dialog_title")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label>{t("purchasing.orders.reject_reason")}</Label>
            <Textarea value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={3} autoFocus />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={!rejectReason.trim() || rejectMutation.isPending}
              onClick={() => rejectMutation.mutate()}
            >
              {rejectMutation.isPending ? t("common.loading") : t("purchasing.orders.reject")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={remainingPromptOpen} onOpenChange={(open) => !open && setRemainingPromptOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("purchasing.orders.remaining_prompt_title")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t("purchasing.orders.remaining_prompt_body")}</p>
          <div className="space-y-1">
            <Label>{t("purchasing.orders.short_close_reason")}</Label>
            <Textarea value={shortCloseReason} onChange={(e) => setShortCloseReason(e.target.value)} rows={3} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemainingPromptOpen(false)}>
              {t("purchasing.orders.will_receive_later")}
            </Button>
            <Button
              variant="destructive"
              disabled={!shortCloseReason.trim() || shortCloseMutation.isPending}
              onClick={() => shortCloseMutation.mutate()}
            >
              {shortCloseMutation.isPending ? t("common.loading") : t("purchasing.orders.short_close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
