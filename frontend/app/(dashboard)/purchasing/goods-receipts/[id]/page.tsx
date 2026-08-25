"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";

/** A Goods Receipt is immutable once created (status="done" the instant
 * it's recorded, per GoodsReceiptService.record_receipt) -- unlike Vendor
 * Bill's detail page, there is no edit/approve/reverse action here, just a
 * read-only record of what was physically received against a PO line. */
export default function GoodsReceiptDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, locale } = useI18n();
  const router = useRouter();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);

  const { data, isLoading } = useQuery({
    queryKey: ["goods-receipt", companyId, id],
    queryFn: () => purchasingApi.getGoodsReceipt(companyId, id),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;

  const { receipt, lines } = data;
  const productLabel = (productId: string) => productsQuery.data?.find((p) => p.id === productId)?.name ?? productId;
  const warehouseLabel =
    warehousesQuery.data?.find((w) => w.id === receipt.warehouse_id)?.name ?? receipt.warehouse_id;

  return (
    <div className="max-w-2xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/purchasing?tab=goods-receipts")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            {receipt.number}
            <Badge variant={statusVariant(receipt.status)}>{receipt.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("purchasing.orders.date")}</dt>
            <dd>{formatDate(receipt.receipt_date, locale)}</dd>
            <dt className="text-muted-foreground">{t("inventory.stock.warehouse")}</dt>
            <dd>{warehouseLabel}</dd>
            <dt className="text-muted-foreground">{t("purchasing.goods_receipts.purchase_order")}</dt>
            <dd>
              <Button
                variant="link"
                className="h-auto p-0"
                onClick={() => router.push(`/purchasing/orders/${receipt.purchase_order_id}`)}
              >
                {t("purchasing.goods_receipts.view_order")}
              </Button>
            </dd>
          </dl>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("purchasing.orders.select_product")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.qty")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>{productLabel(l.product_id)}</TableCell>
                  <TableCell className="text-end">{l.qty}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
