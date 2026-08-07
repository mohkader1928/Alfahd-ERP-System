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
import { AttachmentsPanel } from "@/components/erp/attachments/attachments-panel";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";

export default function VendorBillDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, locale } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);

  const { data, isLoading } = useQuery({
    queryKey: ["vendor-bill", companyId, id],
    queryFn: () => purchasingApi.getVendorBill(companyId, id),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  const vendorsQuery = useQuery({
    queryKey: ["partners", companyId, "vendors"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });

  const approveMutation = useMutation({
    mutationFn: () => purchasingApi.approveVendorBill(companyId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-bill", companyId, id] });
      queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] });
      toastSuccess(t("toast.success_title"), t("purchasing.vendor_bills.approve"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;

  const { bill, lines } = data;
  const productLabel = (productId: string) => productsQuery.data?.find((p) => p.id === productId)?.name ?? productId;
  const vendorLabel = vendorsQuery.data?.find((p) => p.id === bill.partner_id)?.name ?? bill.partner_id;

  return (
    <div className="max-w-2xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/purchasing?tab=bills")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            {bill.number}
            <div className="flex gap-1">
              <Badge variant={statusVariant(bill.status)}>{bill.status}</Badge>
              {bill.mismatch_reasons && <Badge variant="destructive">{t("purchasing.vendor_bills.mismatch")}</Badge>}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("purchasing.orders.vendor")}</dt>
            <dd>{vendorLabel}</dd>
            <dt className="text-muted-foreground">{t("purchasing.orders.date")}</dt>
            <dd>{formatDate(bill.bill_date, locale)}</dd>
            {bill.vendor_reference && (
              <>
                <dt className="text-muted-foreground">{t("purchasing.vendor_bills.vendor_reference")}</dt>
                <dd>{bill.vendor_reference}</dd>
              </>
            )}
            <dt className="text-muted-foreground">{t("purchasing.vendor_bills.subtotal")}</dt>
            <dd>{formatCurrency(bill.subtotal_amount)}</dd>
            <dt className="text-muted-foreground">{t("purchasing.vendor_bills.tax")}</dt>
            <dd>{formatCurrency(bill.tax_amount)}</dd>
            <dt className="text-muted-foreground">{t("purchasing.orders.total")}</dt>
            <dd>{formatCurrency(bill.total_amount)}</dd>
          </dl>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("purchasing.orders.select_product")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.qty")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.unit_price")}</TableHead>
                <TableHead className="text-end">{t("purchasing.orders.total")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => (
                <TableRow key={l.id}>
                  <TableCell>{productLabel(l.product_id)}</TableCell>
                  <TableCell className="text-end">{l.qty}</TableCell>
                  <TableCell className="text-end">{formatCurrency(l.unit_price)}</TableCell>
                  <TableCell className="text-end">{formatCurrency(l.line_total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {bill.status !== "posted" && (
            <Can permission="purchasing.vendor_bill.approve">
              <Button onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
                {approveMutation.isPending ? t("common.loading") : t("purchasing.vendor_bills.approve")}
              </Button>
            </Can>
          )}

          <AttachmentsPanel entityType="vendor_bill" entityId={bill.id} />
        </CardContent>
      </Card>
    </div>
  );
}
