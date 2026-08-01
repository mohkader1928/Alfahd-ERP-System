"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { salesApi } from "@/features/sales/api/client";
import { ApiError } from "@/lib/api-client";

export default function SalesOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const router = useRouter();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const { data: order, isLoading } = useQuery({
    queryKey: ["sales-order", companyId, id],
    queryFn: () => salesApi.getSalesOrder(companyId, id),
  });

  const invoiceMutation = useMutation({
    mutationFn: () => salesApi.issueInvoice(companyId, branchId, id),
    onSuccess: (result) => router.push(`/sales/invoices/${result.invoice.id}`),
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!order) return null;

  return (
    <div className="max-w-xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/sales/quotations")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            {order.number}
            <Badge variant={order.status === "confirmed" ? "default" : "secondary"}>{order.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("sales.quotations.date")}</dt>
            <dd>{order.order_date}</dd>
            <dt className="text-muted-foreground">{t("sales.quotations.total")}</dt>
            <dd>{order.total_amount}</dd>
          </dl>
          {order.status === "confirmed" && (
            <Button onClick={() => invoiceMutation.mutate()} disabled={invoiceMutation.isPending}>
              {invoiceMutation.isPending ? t("common.loading") : t("sales.orders.invoice")}
            </Button>
          )}
          {invoiceMutation.isError && (
            <p className="text-sm text-destructive">
              {invoiceMutation.error instanceof ApiError ? invoiceMutation.error.detail : t("common.error")}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
