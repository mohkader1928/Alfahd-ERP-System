"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookOpenText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Can } from "@/components/erp/permissions/can";
import { AttachmentsPanel } from "@/components/erp/attachments/attachments-panel";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
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
  const [debitNoteReason, setDebitNoteReason] = useState("");
  const [debitNoteRestock, setDebitNoteRestock] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editVendorReference, setEditVendorReference] = useState("");
  const [editLines, setEditLines] = useState<{ purchase_order_line_id: string; qty: string; unit_price: string }[]>(
    []
  );
  const [editError, setEditError] = useState<string | null>(null);

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
  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
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

  const debitNoteMutation = useMutation({
    mutationFn: () => purchasingApi.issueDebitNote(companyId, branchId!, id, debitNoteReason, debitNoteRestock),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["vendor-bill", companyId, id] });
      queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] });
      toastSuccess(t("toast.success_title"), result.number);
      router.push(`/purchasing/bills/${result.id}`);
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      purchasingApi.updateVendorBill(companyId, branchId!, id, {
        vendor_reference: editVendorReference || undefined,
        lines: editLines,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendor-bill", companyId, id] });
      queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] });
      toastSuccess(t("toast.success_title"), t("common.edit"));
      setIsEditing(false);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setEditError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  function startEditing() {
    if (!data) return;
    setEditVendorReference(data.bill.vendor_reference ?? "");
    // Only ever shown for a bill_type='standard' bill, where every line is
    // guaranteed a real purchase_order_line_id (3-way match requires it) —
    // the field is nullable on the type only because a freeform Purchase
    // Return line has none.
    setEditLines(
      data.lines.map((l) => ({
        purchase_order_line_id: l.purchase_order_line_id as string,
        qty: l.qty,
        unit_price: l.unit_price,
      }))
    );
    setEditError(null);
    setIsEditing(true);
  }

  function updateEditLine(index: number, patch: Partial<{ qty: string; unit_price: string }>) {
    setEditLines((prev) => prev.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

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
              {bill.bill_type === "debit_note" && <Badge variant="secondary">{t("purchasing.vendor_bills.debit_note")}</Badge>}
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
            <dt className="text-muted-foreground">{t("inventory.stock.warehouse")}</dt>
            <dd>
              {warehousesQuery.data?.find((w) => w.id === bill.warehouse_id)?.name ?? bill.warehouse_id ?? "—"}
            </dd>
            {!isEditing && bill.vendor_reference && (
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

          {isEditing ? (
            <div className="space-y-3 border-t pt-4">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">{t("purchasing.vendor_bills.vendor_reference")}</label>
                <Input value={editVendorReference} onChange={(e) => setEditVendorReference(e.target.value)} />
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("purchasing.orders.select_product")}</TableHead>
                    <TableHead className="text-end">{t("purchasing.orders.qty")}</TableHead>
                    <TableHead className="text-end">{t("purchasing.orders.unit_price")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lines.map((l, index) => (
                    <TableRow key={l.id}>
                      <TableCell>{productLabel(l.product_id)}</TableCell>
                      <TableCell className="text-end">
                        <Input
                          className="w-24 text-end"
                          value={editLines[index]?.qty ?? ""}
                          onChange={(e) => updateEditLine(index, { qty: e.target.value })}
                        />
                      </TableCell>
                      <TableCell className="text-end">
                        <Input
                          className="w-28 text-end"
                          value={editLines[index]?.unit_price ?? ""}
                          onChange={(e) => updateEditLine(index, { unit_price: e.target.value })}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {editError && <p className="text-sm text-destructive">{editError}</p>}
              <div className="flex gap-2">
                <Button onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}>
                  {updateMutation.isPending ? t("common.loading") : t("common.save")}
                </Button>
                <Button variant="outline" onClick={() => setIsEditing(false)}>
                  {t("common.cancel")}
                </Button>
              </div>
            </div>
          ) : (
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
          )}

          {!isEditing && bill.status !== "posted" && bill.bill_type === "standard" && (
            <Can permission="purchasing.vendor_bill.update">
              <Button variant="outline" size="sm" onClick={startEditing}>
                {t("common.edit")}
              </Button>
            </Can>
          )}

          {!isEditing && bill.journal_entry_id && (
            <Can permission="accounting.journal_entry.view">
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push(`/accounting/journal-entries/${bill.journal_entry_id}`)}
              >
                <BookOpenText className="h-4 w-4" />
                {t("common.view_journal_entry")}
              </Button>
            </Can>
          )}

          {!isEditing && bill.status !== "posted" && (
            <Can permission="purchasing.vendor_bill.approve">
              <Button onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
                {approveMutation.isPending ? t("common.loading") : t("purchasing.vendor_bills.approve")}
              </Button>
            </Can>
          )}

          {bill.status === "posted" && bill.bill_type === "standard" && (
            <Can permission="purchasing.vendor_bill.debit_note">
              <div className="space-y-2 border-t pt-4">
                <Input
                  placeholder={t("purchasing.vendor_bills.debit_note_reason_placeholder")}
                  value={debitNoteReason}
                  onChange={(e) => setDebitNoteReason(e.target.value)}
                />
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={debitNoteRestock}
                    onChange={(e) => setDebitNoteRestock(e.target.checked)}
                  />
                  {t("purchasing.vendor_bills.restock_label")}
                </label>
                <Button
                  variant="outline"
                  onClick={() => debitNoteMutation.mutate()}
                  disabled={!debitNoteReason || debitNoteMutation.isPending}
                >
                  {debitNoteMutation.isPending ? t("common.loading") : t("purchasing.vendor_bills.debit_note")}
                </Button>
                {debitNoteMutation.isError && (
                  <p className="text-sm text-destructive">
                    {debitNoteMutation.error instanceof ApiError ? debitNoteMutation.error.detail : t("common.error")}
                  </p>
                )}
              </div>
            </Can>
          )}

          <AttachmentsPanel entityType="vendor_bill" entityId={bill.id} />
        </CardContent>
      </Card>
    </div>
  );
}
