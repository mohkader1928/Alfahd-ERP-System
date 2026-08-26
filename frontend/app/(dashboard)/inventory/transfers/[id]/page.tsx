"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorState } from "@/components/erp/states/error-state";
import { NotFoundState } from "@/components/erp/states/not-found";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { ApiError } from "@/lib/api-client";
import { formatDate } from "@/lib/format-date";
import { formatQty } from "@/lib/format-qty";

/** A Stock Transfer has no draft/approve workflow -- both legs post the
 * instant it's created (InventoryValuationService.issue_stock/receive_stock
 * inside the same request), so there is no action button here, unlike
 * Cycle Count's detail page. */
export default function StockTransferDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, locale } = useI18n();
  const router = useRouter();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["stock-transfer", companyId, id],
    queryFn: () => inventoryApi.getTransfer(companyId, id),
  });
  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  const sourceLocationsQuery = useQuery({
    queryKey: ["locations", companyId, data?.transfer.source_warehouse_id],
    queryFn: () => inventoryApi.listLocations(companyId, data!.transfer.source_warehouse_id),
    enabled: !!data?.transfer.source_warehouse_id,
  });
  const destLocationsQuery = useQuery({
    queryKey: ["locations", companyId, data?.transfer.dest_warehouse_id],
    queryFn: () => inventoryApi.listLocations(companyId, data!.transfer.dest_warehouse_id),
    enabled: !!data?.transfer.dest_warehouse_id,
  });

  if (isError && error instanceof ApiError && error.status === 404) {
    return <NotFoundState label={t("inventory.transfers.not_found")} />;
  }
  if (isError) {
    return <ErrorState onRetry={() => refetch()} />;
  }
  if (isLoading || !data) return <Skeleton className="h-40 w-full" />;

  const { transfer, lines } = data;
  const productLabel = (productId: string) => productsQuery.data?.find((p) => p.id === productId)?.name ?? productId;
  const sourceWarehouseLabel =
    warehousesQuery.data?.find((w) => w.id === transfer.source_warehouse_id)?.name ?? transfer.source_warehouse_id;
  const destWarehouseLabel =
    warehousesQuery.data?.find((w) => w.id === transfer.dest_warehouse_id)?.name ?? transfer.dest_warehouse_id;
  const sourceLocationLabel = (locationId: string) =>
    sourceLocationsQuery.data?.find((l) => l.id === locationId)?.name ?? locationId;
  const destLocationLabel = (locationId: string) =>
    destLocationsQuery.data?.find((l) => l.id === locationId)?.name ?? locationId;

  return (
    <div className="max-w-2xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/inventory?tab=transfers")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{transfer.number}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("inventory.transfers.date")}</dt>
            <dd>{formatDate(transfer.transfer_date, locale)}</dd>
            <dt className="text-muted-foreground">{t("inventory.transfer.source")}</dt>
            <dd>{sourceWarehouseLabel}</dd>
            <dt className="text-muted-foreground">{t("inventory.transfer.dest")}</dt>
            <dd>{destWarehouseLabel}</dd>
          </dl>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("inventory.stock.product")}</TableHead>
                <TableHead>{t("inventory.transfers.source_location")}</TableHead>
                <TableHead>{t("inventory.transfers.dest_location")}</TableHead>
                <TableHead className="text-end">{t("inventory.transfer.qty")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>{productLabel(l.product_id)}</TableCell>
                  <TableCell>{sourceLocationLabel(l.source_location_id)}</TableCell>
                  <TableCell>{destLocationLabel(l.dest_location_id)}</TableCell>
                  <TableCell className="text-end">{formatQty(l.qty)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
