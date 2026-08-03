"use client";

import { use } from "react";
import Link from "next/link";
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
import { paymentsApi } from "@/features/payments/api/client";
import { salesApi } from "@/features/sales/api/client";
import type { PaymentAllocation } from "@/features/payments/api/types";
import { formatCurrency } from "@/lib/format-currency";

// Resolves a real invoice number (never a raw UUID) for sales-invoice
// allocations; vendor bills have no detail screen yet (see
// docs/17f-subledgers-and-aging.md's known limitations), so they show a
// short, clearly-labeled reference instead of the full id.
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
  return (
    <span className="text-muted-foreground">
      {t("payments.allocation.vendor_bill")} {allocation.vendor_bill_id?.slice(0, 8)}
    </span>
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

  const { data, isLoading } = useQuery({
    queryKey: ["payment", companyId, id],
    queryFn: () => paymentsApi.getPayment(companyId, id),
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!data) return null;

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
