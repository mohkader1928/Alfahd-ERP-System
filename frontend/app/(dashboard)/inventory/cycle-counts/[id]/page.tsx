"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format-date";
import { formatQty } from "@/lib/format-qty";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";

export default function CycleCountDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, locale } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const [downloading, setDownloading] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["cycle-count", companyId, id],
    queryFn: () => inventoryApi.getCycleCount(companyId, id),
  });
  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  const locationsQuery = useQuery({
    queryKey: ["locations", companyId, data?.cycle_count.warehouse_id],
    queryFn: () => inventoryApi.listLocations(companyId, data!.cycle_count.warehouse_id),
    enabled: !!data?.cycle_count.warehouse_id,
  });

  const approveMutation = useMutation({
    mutationFn: () => inventoryApi.approveCycleCount(companyId, branchId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cycle-count", companyId, id] });
      queryClient.invalidateQueries({ queryKey: ["cycle-counts", companyId] });
      queryClient.invalidateQueries({ queryKey: ["stock-quants", companyId] });
      toastSuccess(t("toast.success_title"), t("inventory.cycle_counts.approve"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  async function handleDownloadPdf() {
    setDownloading(true);
    try {
      const { blob, filename } = await inventoryApi.downloadCycleCountPdf(companyId, id, locale);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `${data?.cycle_count.number ?? "cycle-count"}.pdf`;
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

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;

  const { cycle_count, lines } = data;
  const productLabel = (productId: string) => productsQuery.data?.find((p) => p.id === productId)?.name ?? productId;
  const locationLabel = (locationId: string) => locationsQuery.data?.find((l) => l.id === locationId)?.name ?? locationId;
  const warehouseLabel = warehousesQuery.data?.find((w) => w.id === cycle_count.warehouse_id)?.name ?? cycle_count.warehouse_id;

  return (
    <div className="max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => router.push("/inventory?tab=cycle-counts")}>
          <ArrowLeft className="h-4 w-4" />
          {t("common.back")}
        </Button>
        <Button variant="outline" size="sm" onClick={handleDownloadPdf} disabled={downloading}>
          <Download className="h-4 w-4" />
          {downloading ? t("common.loading") : t("inventory.cycle_counts.download_pdf")}
        </Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>
              {cycle_count.number} <span className="text-muted-foreground font-normal">— {warehouseLabel}</span>
            </span>
            <Badge variant={statusVariant(cycle_count.status)}>{cycle_count.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("inventory.cycle_counts.scheduled_date")}</dt>
            <dd>{formatDate(cycle_count.scheduled_date, locale)}</dd>
          </dl>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("inventory.stock.product")}</TableHead>
                <TableHead>{t("inventory.cycle_counts.location")}</TableHead>
                <TableHead className="text-end">{t("inventory.cycle_counts.system_qty")}</TableHead>
                <TableHead className="text-end">{t("inventory.cycle_counts.counted_qty")}</TableHead>
                <TableHead className="text-end">{t("inventory.cycle_counts.variance")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => {
                const variance = Number(l.counted_qty) - Number(l.system_qty);
                return (
                  <TableRow key={l.id}>
                    <TableCell>{productLabel(l.product_id)}</TableCell>
                    <TableCell>{locationLabel(l.location_id)}</TableCell>
                    <TableCell className="text-end">{formatQty(l.system_qty)}</TableCell>
                    <TableCell className="text-end">{formatQty(l.counted_qty)}</TableCell>
                    <TableCell
                      className={cn(
                        "text-end",
                        variance < 0 && "text-destructive",
                        variance === 0 && "text-muted-foreground"
                      )}
                    >
                      {variance > 0 ? `+${formatQty(variance)}` : formatQty(variance)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {cycle_count.status !== "approved" && (
            <Can permission="inventory.cycle_count.manage">
              <Button onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
                {approveMutation.isPending ? t("common.loading") : t("inventory.cycle_counts.approve")}
              </Button>
            </Can>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
