"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";

interface ReturnLine {
  product_id: string;
  tax_rate_id: string;
  original_qty: string;
  original_unit_price: string;
  returned_qty: string;
  price: string;
}

// Owner request: a Purchase Return starts from a real vendor bill, not a
// blank line editor — pick the bill, its lines (product, qty purchased,
// price) load automatically, the user enters a returned quantity per line
// (defaulting to 0 = not returned) and may override the price (defaults
// to the original bill price). Only lines with returned qty > 0 are
// submitted.
export default function NewPurchaseReturnPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [billId, setBillId] = useState("");
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(true);
  const [returnLines, setReturnLines] = useState<ReturnLine[]>([]);
  const [loadedBillId, setLoadedBillId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const vendorsQuery = useQuery({
    queryKey: ["partners", companyId, "vendor"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { vendorsOnly: true }),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  // Only a posted, standard bill can be returned against (the service
  // rejects anything else).
  const billsQuery = useQuery({
    queryKey: ["vendor-bills", companyId, "returnable"],
    queryFn: () => purchasingApi.listVendorBills(companyId, { pageSize: 200 }),
  });
  const returnableBills = (billsQuery.data?.items ?? []).filter(
    (bill) => bill.bill_type === "standard" && bill.status === "posted" && (!partnerId || bill.partner_id === partnerId)
  );

  const billDetailQuery = useQuery({
    queryKey: ["vendor-bill-detail", companyId, billId],
    queryFn: () => purchasingApi.getVendorBill(companyId, billId),
    enabled: !!billId,
  });

  // Reset the editable line table whenever a freshly-fetched bill arrives —
  // a conditional setState during render (not an effect), the
  // React-documented way to reset local state when an external data
  // source changes: https://react.dev/learn/you-might-not-need-an-effect
  if (billDetailQuery.data && billDetailQuery.data.bill.id !== loadedBillId) {
    setLoadedBillId(billDetailQuery.data.bill.id);
    setReturnLines(
      billDetailQuery.data.lines.map((line) => ({
        product_id: line.product_id,
        tax_rate_id: line.tax_rate_id,
        original_qty: line.qty,
        original_unit_price: line.unit_price,
        returned_qty: "0",
        price: line.unit_price,
      }))
    );
  }

  function updateReturnedQty(index: number, value: string) {
    setReturnLines((prev) => prev.map((l, i) => (i === index ? { ...l, returned_qty: value } : l)));
  }

  function updatePrice(index: number, value: string) {
    setReturnLines((prev) => prev.map((l, i) => (i === index ? { ...l, price: value } : l)));
  }

  const linesToReturn = returnLines.filter((l) => Number(l.returned_qty) > 0);

  const createMutation = useMutation({
    mutationFn: () =>
      purchasingApi.issueDebitNoteForLines(companyId, branchId, {
        partner_id: billDetailQuery.data!.bill.partner_id,
        original_bill_id: billId,
        reason,
        restock,
        lines: linesToReturn.map((l) => ({
          product_id: l.product_id,
          qty: l.returned_qty,
          unit_price: l.price,
          tax_rate_id: l.tax_rate_id,
        })),
      }),
    onSuccess: (bill) => {
      queryClient.invalidateQueries({ queryKey: ["purchase-returns", companyId] });
      queryClient.invalidateQueries({ queryKey: ["vendor-bills", companyId] });
      router.push(`/purchasing/bills/${bill.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const productLabel = (productId: string) => {
    const product = productsQuery.data?.find((p) => p.id === productId);
    return product ? { code: product.sku, name: product.name, image: product.image_path } : { code: "", name: productId, image: null };
  };

  const canSubmit =
    !!billId &&
    !!reason &&
    linesToReturn.length > 0 &&
    linesToReturn.every((l) => Number(l.returned_qty) > 0 && l.price !== "") &&
    !createMutation.isPending;

  return (
    <div className="max-w-3xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/purchasing/returns")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{t("purchasing.returns.new")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>{t("purchasing.orders.vendor")}</Label>
            <Select
              value={partnerId}
              onValueChange={(v) => {
                setPartnerId(v ?? "");
                setBillId("");
                setReturnLines([]);
                setLoadedBillId(null);
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("purchasing.orders.select_vendor")}>
                  {(value: string) => {
                    const partner = vendorsQuery.data?.find((p) => p.id === value);
                    return partner ? (
                      <span className="flex items-center gap-2">
                        <EntityImage src={partner.image_path} name={partner.name} size="xs" />
                        {partner.name}
                      </span>
                    ) : (
                      value
                    );
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {vendorsQuery.data?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    <span className="flex items-center gap-2">
                      <EntityImage src={p.image_path} name={p.name} size="xs" />
                      {p.name}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>{t("purchasing.returns.select_bill")}</Label>
            <Select value={billId} onValueChange={(v) => setBillId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("purchasing.returns.select_bill")}>
                  {(value: string) => {
                    const bill = returnableBills.find((b) => b.id === value);
                    return bill ? `${bill.number} — ${formatCurrency(bill.total_amount)}` : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {returnableBills.map((bill) => (
                  <SelectItem key={bill.id} value={bill.id}>
                    {bill.number} — {formatCurrency(bill.total_amount)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {billId && billDetailQuery.isLoading && (
            <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
          )}

          {returnLines.length > 0 && (
            <div className="space-y-2">
              <Label>{t("purchasing.returns.lines_title")}</Label>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("purchasing.orders.select_product")}</TableHead>
                    <TableHead className="text-end">{t("purchasing.returns.original_qty")}</TableHead>
                    <TableHead className="text-end">{t("purchasing.returns.original_price")}</TableHead>
                    <TableHead className="text-end w-28">{t("purchasing.returns.returned_qty")}</TableHead>
                    <TableHead className="text-end w-28">{t("purchasing.returns.return_price")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {returnLines.map((line, index) => {
                    const product = productLabel(line.product_id);
                    return (
                      <TableRow key={index}>
                        <TableCell>
                          <span className="flex items-center gap-2">
                            <EntityImage src={product.image} name={product.name} size="xs" />
                            <span>
                              <span className="text-xs text-muted-foreground">{product.code}</span>{" "}
                              {product.name}
                            </span>
                          </span>
                        </TableCell>
                        <TableCell className="text-end">{line.original_qty}</TableCell>
                        <TableCell className="text-end">{formatCurrency(line.original_unit_price)}</TableCell>
                        <TableCell>
                          <Input
                            className="text-end"
                            value={line.returned_qty}
                            onChange={(e) => updateReturnedQty(index, e.target.value)}
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            className="text-end"
                            value={line.price}
                            onChange={(e) => updatePrice(index, e.target.value)}
                          />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}

          <div className="space-y-2">
            <Label>{t("purchasing.returns.reason")}</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("purchasing.returns.reason")} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={restock} onChange={(e) => setRestock(e.target.checked)} />
            {t("purchasing.vendor_bills.restock_label")}
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!canSubmit}
          >
            {createMutation.isPending ? t("common.loading") : t("purchasing.returns.new")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
