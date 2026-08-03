"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";

function OrdersTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const ordersQuery = useQuery({
    queryKey: ["purchase-orders", companyId],
    queryFn: () => purchasingApi.listOrders(companyId),
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{t("purchasing.orders.title")}</CardTitle>
          <Button size="sm" render={<Link href="/purchasing/orders/new" />}>
            <Plus className="h-4 w-4" />
            {t("purchasing.orders.new")}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("purchasing.orders.number")}</TableHead>
              <TableHead>{t("purchasing.orders.date")}</TableHead>
              <TableHead>{t("purchasing.orders.status")}</TableHead>
              <TableHead className="text-end">{t("purchasing.orders.total")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!ordersQuery.isLoading && ordersQuery.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {ordersQuery.data?.map((o) => (
              <TableRow key={o.id}>
                <TableCell>
                  <Link href={`/purchasing/orders/${o.id}`} className="font-medium underline-offset-4 hover:underline">
                    {o.number}
                  </Link>
                </TableCell>
                <TableCell>{o.order_date}</TableCell>
                <TableCell>
                  <Badge variant={statusVariant(o.status)}>{o.status}</Badge>
                </TableCell>
                <TableCell className="text-end">{formatCurrency(o.total_amount)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function VendorBillsTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const billsQuery = useQuery({
    queryKey: ["vendor-bills", companyId],
    queryFn: () => purchasingApi.listVendorBills(companyId),
  });

  const approveMutation = useMutation({
    mutationFn: (id: string) => purchasingApi.approveVendorBill(companyId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] });
      toastSuccess(t("toast.success_title"), t("purchasing.vendor_bills.approve"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  if (billsQuery.isLoading) return <Skeleton className="h-40 w-full" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("purchasing.vendor_bills.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("purchasing.orders.number")}</TableHead>
              <TableHead>{t("purchasing.orders.status")}</TableHead>
              <TableHead className="text-end">{t("purchasing.orders.total")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {billsQuery.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {billsQuery.data?.map((b) => (
              <TableRow key={b.id}>
                <TableCell>{b.number}</TableCell>
                <TableCell className="space-x-1">
                  <Badge variant={statusVariant(b.status)}>{b.status}</Badge>
                  {b.mismatch_reasons && <Badge variant="destructive">{t("purchasing.vendor_bills.mismatch")}</Badge>}
                </TableCell>
                <TableCell className="text-end">{formatCurrency(b.total_amount)}</TableCell>
                <TableCell className="text-end">
                  {b.status !== "posted" && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => approveMutation.mutate(b.id)}
                      disabled={approveMutation.isPending}
                    >
                      {t("purchasing.vendor_bills.approve")}
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {approveMutation.isError && (
          <p className="mt-2 text-sm text-destructive">
            {approveMutation.error instanceof ApiError ? approveMutation.error.detail : t("common.error")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function PurchasingPage() {
  const { t } = useI18n();
  // See the same note in accounting/page.tsx — Base UI's Tabs.Panel doesn't
  // reliably hide inactive panels once a second one mounts, so the active
  // tab is tracked ourselves and gates each panel's content directly.
  const [tab, setTab] = useState("orders");
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t("nav.purchasing")}</h1>
      <Tabs value={tab} onValueChange={(v) => setTab(v as string)}>
        <TabsList>
          <TabsTrigger value="orders">{t("purchasing.orders.title")}</TabsTrigger>
          <TabsTrigger value="bills">{t("purchasing.vendor_bills.title")}</TabsTrigger>
        </TabsList>
        <TabsContent value="orders">{tab === "orders" && <OrdersTab />}</TabsContent>
        <TabsContent value="bills">{tab === "bills" && <VendorBillsTab />}</TabsContent>
      </Tabs>
    </div>
  );
}
