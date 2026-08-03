"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
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

  const { data: quotation, isLoading } = useQuery({
    queryKey: ["quotation", companyId, id],
    queryFn: () => salesApi.getQuotation(companyId, id),
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
  if (!quotation) return null;

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
          {quotation.status === "draft" && (
            <Button onClick={() => confirmMutation.mutate()} disabled={confirmMutation.isPending}>
              {confirmMutation.isPending ? t("common.loading") : t("sales.quotations.confirm")}
            </Button>
          )}
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
