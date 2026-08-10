"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Can } from "@/components/erp/permissions/can";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { salesApi } from "@/features/sales/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";

export default function QuotationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const { data, isLoading } = useQuery({
    queryKey: ["quotation", companyId, id],
    queryFn: () => salesApi.getQuotation(companyId, id),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
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

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;
  const { quotation, lines } = data;
  const productLabel = (productId: string) => productsQuery.data?.find((p) => p.id === productId)?.name ?? productId;

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
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("sales.quotations.date")}</dt>
            <dd>{quotation.quote_date}</dd>
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
              {lines.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>{productLabel(l.product_id)}</TableCell>
                  <TableCell className="text-end">{l.qty}</TableCell>
                  <TableCell className="text-end">{formatCurrency(l.unit_price)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
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
    </div>
  );
}
