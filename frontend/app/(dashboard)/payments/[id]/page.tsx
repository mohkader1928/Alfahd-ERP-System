"use client";

import { use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BookOpenText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Can } from "@/components/erp/permissions/can";
import { ErrorState } from "@/components/erp/states/error-state";
import { NotFoundState } from "@/components/erp/states/not-found";
import { PermissionDenied } from "@/components/erp/states/permission-denied";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { paymentsApi } from "@/features/payments/api/client";
import { salesApi } from "@/features/sales/api/client";
import type { PaymentAllocation } from "@/features/payments/api/types";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { sourceDocumentHref } from "@/lib/source-document-links";

// Resolves a real invoice number (never a raw UUID) for sales-invoice
// allocations. Vendor-bill allocations link out via the shared
// sourceDocumentHref helper -- purchasing/bills/[id] now exists, matching
// every other screen (General Ledger, Subledgers, VAT Detail) that already
// resolves vendor_bill sources through this same map.
function AllocationDocumentCell({ allocation, companyId }: { allocation: PaymentAllocation; companyId: string }) {
  const { t } = useI18n();
  const invoiceQuery = useQuery({
    queryKey: ["sales-invoice", companyId, allocation.sales_invoice_id],
    queryFn: () => salesApi.getInvoice(companyId, allocation.sales_invoice_id as string),
    enabled: !!allocation.sales_invoice_id,
  });

  if (allocation.sales_invoice_id) {
    return (
      <Link href={`/sales/invoices/${allocation.sales_invoice_id}`} className="underline-offset-4 hover:underline">
        {invoiceQuery.data?.invoice.number ?? t("common.loading")}
      </Link>
    );
  }
  const vendorBillHref = allocation.vendor_bill_id
    ? sourceDocumentHref("vendor_bill", allocation.vendor_bill_id)
    : null;
  const vendorBillLabel = `${t("payments.allocation.vendor_bill")} ${allocation.vendor_bill_id?.slice(0, 8) ?? ""}`;
  return vendorBillHref ? (
    <Link href={vendorBillHref} className="underline-offset-4 hover:underline">
      {vendorBillLabel}
    </Link>
  ) : (
    <span className="text-muted-foreground">{vendorBillLabel}</span>
  );
}

// Milestone 1b: the drill-down destination for a Subledger/General Ledger
// "payment" movement — did not exist before this Milestone (Payments only
// had a list + create screen). Kept minimal and consistent with the
// existing Journal Entry detail page's layout, not a new pattern.
export default function PaymentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const router = useRouter();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["payment", companyId, id],
    queryFn: () => paymentsApi.getPayment(companyId, id),
  });

  if (isError && error instanceof ApiError && error.status === 404) {
    return <NotFoundState label={t("payments.not_found")} />;
  }
  if (isError && error instanceof ApiError && error.status === 403) {
    return <PermissionDenied />;
  }
  if (isError) {
    return <ErrorState onRetry={() => refetch()} />;
  }
  if (isLoading || !data) return <Skeleton className="h-40 w-full" />;

  const { payment, allocations } = data;

  return (
    <div className="max-w-2xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/payments")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            {payment.number}
            <Badge>{t(`payments.type.${payment.payment_type}`)}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted-foreground">{t("payments.date")}</dt>
            <dd>{payment.payment_date}</dd>
            <dt className="text-muted-foreground">{t("payments.amount")}</dt>
            <dd>{formatCurrency(payment.amount, payment.currency_code)}</dd>
            {payment.reference && (
              <>
                <dt className="text-muted-foreground">{t("payments.reference")}</dt>
                <dd>{payment.reference}</dd>
              </>
            )}
          </dl>
          {payment.journal_entry_id && (
            <Can permission="accounting.journal_entry.view">
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push(`/accounting/journal-entries/${payment.journal_entry_id}`)}
              >
                <BookOpenText className="h-4 w-4" />
                {t("common.view_journal_entry")}
              </Button>
            </Can>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("payments.allocation.document")}</TableHead>
                <TableHead className="text-end">{t("payments.allocation.amount")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {allocations.map((a) => (
                <TableRow key={a.id}>
                  <TableCell>
                    <AllocationDocumentCell allocation={a} companyId={companyId} />
                  </TableCell>
                  <TableCell className="text-end">{formatCurrency(a.amount, payment.currency_code)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
