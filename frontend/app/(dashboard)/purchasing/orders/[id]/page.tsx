"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("purchasing.orders.confirm"));
    },
    onError: handleError,
  });

  const receiveMutation = useMutation({
    mutationFn: () => {
      const remaining = data!.lines
        .map((l) => ({ purchase_order_line_id: l.id, qty: String(Number(l.qty) - Number(l.qty_received)) }))
        .filter((l) => Number(l.qty) > 0);
      return purchasingApi.recordGoodsReceipt(companyId, branchId, id, { lines: remaining });
    },
    onSuccess: () => {
      invalidate();
      toastSuccess(t("toast.success_title"), t("purchasing.orders.receive_all"));
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
  const hasRemainingToReceive = lines.some((l) => Number(l.qty_received) < Number(l.qty));
  const hasReceivedUnbilled = lines.some((l) => Number(l.qty_billed) < Number(l.qty_received));

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
            <Badge variant={statusVariant(order.status)}>{order.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("purchasing.orders.date")}</dt>
            <dd>{order.order_date}</dd>
            <dt className="text-muted-foreground">{t("purchasing.orders.total")}</dt>
            <dd>{formatCurrency(order.total_amount)}</dd>
          </dl>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("purchasing.orders.select_product")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.qty")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.received")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.billed")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>{productLabel(l.product_id)}</TableCell>
                  <TableCell className="text-end">{l.qty}</TableCell>
                  <TableCell className="text-end">{l.qty_received}</TableCell>
                  <TableCell className="text-end">{l.qty_billed}</TableCell>
                </TableRow>
              ))}
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
            {order.status === "confirmed" && hasRemainingToReceive && (
              <Can permission="purchasing.goods_receipt.create">
                <Button onClick={() => receiveMutation.mutate()} disabled={receiveMutation.isPending}>
                  {receiveMutation.isPending ? t("common.loading") : t("purchasing.orders.receive_all")}
                </Button>
              </Can>
            )}
            {order.status === "confirmed" && hasReceivedUnbilled && (
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
          </div>
          {actionError && <p className="text-sm text-destructive">{actionError}</p>}

          <AttachmentsPanel entityType="purchase_order" entityId={order.id} />
        </CardContent>
      </Card>
    </div>
  );
}
