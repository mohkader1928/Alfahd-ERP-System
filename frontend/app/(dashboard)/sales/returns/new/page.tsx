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
import { salesApi } from "@/features/sales/api/client";
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

// Owner request: a Sales Return starts from a real invoice, not a blank
// line editor — pick the invoice, its lines (product, qty sold, price)
// load automatically, the user enters a returned quantity per line
// (defaulting to 0 = not returned) and may override the price (defaults
// to the original invoice price). Only lines with returned qty > 0 are
// submitted.
export default function NewSalesReturnPage() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [partnerId, setPartnerId] = useState("");
  const [invoiceId, setInvoiceId] = useState("");
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(true);
  const [returnLines, setReturnLines] = useState<ReturnLine[]>([]);
  const [loadedInvoiceId, setLoadedInvoiceId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Stable per-mount key: a retried/duplicate submission of the SAME
  // return (double-click, network retry, resubmission after an unclear
  // result) reuses this key so the backend's idempotency guard replays
  // the first response instead of posting a second full GL reversal +
  // restock -- same defect class fixed on the Purchasing side after a
  // real, reported Inventory Valuation vs GL gap.
  const [returnIdempotencyKey] = useState(() => crypto.randomUUID());

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, "customers"],
    queryFn: () => identityApi.listPartners(companyId, branchId, { customersOnly: true }),
  });
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  // Only a tax/simplified invoice can be returned against (the service
  // rejects anything else).
  const invoicesQuery = useQuery({
    queryKey: ["sales-invoices", companyId, "returnable"],
    queryFn: () => salesApi.listInvoices(companyId, { pageSize: 200 }),
  });
  const returnableInvoices = (invoicesQuery.data?.items ?? []).filter(
    (inv) =>
      (inv.invoice_type === "tax" || inv.invoice_type === "simplified") &&
      (!partnerId || inv.partner_id === partnerId)
  );

  const invoiceDetailQuery = useQuery({
    queryKey: ["sales-invoice-detail", companyId, invoiceId],
    queryFn: () => salesApi.getInvoice(companyId, invoiceId),
    enabled: !!invoiceId,
  });

  // Reset the editable line table whenever a freshly-fetched invoice
  // arrives — a conditional setState during render (not an effect), the
  // React-documented way to reset local state when an external data
  // source changes: https://react.dev/learn/you-might-not-need-an-effect
  if (invoiceDetailQuery.data && invoiceDetailQuery.data.invoice.id !== loadedInvoiceId) {
    setLoadedInvoiceId(invoiceDetailQuery.data.invoice.id);
    setReturnLines(
      invoiceDetailQuery.data.lines.map((line) => ({
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
      salesApi.issueCreditNoteForLines(
        companyId,
        branchId,
        {
          partner_id: invoiceDetailQuery.data!.invoice.partner_id,
          original_invoice_id: invoiceId,
          reason,
          restock,
          lines: linesToReturn.map((l) => ({
            product_id: l.product_id,
            qty: l.returned_qty,
            unit_price: l.price,
            tax_rate_id: l.tax_rate_id,
          })),
        },
        returnIdempotencyKey
      ),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["sales-returns", companyId] });
      queryClient.invalidateQueries({ queryKey: ["sales-invoices", companyId] });
      router.push(`/sales/invoices/${result.invoice.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const productLabel = (productId: string) => {
    const product = productsQuery.data?.find((p) => p.id === productId);
    return product ? { code: product.sku, name: product.name, image: product.image_path } : { code: "", name: productId, image: null };
  };

  const canSubmit =
    !!invoiceId &&
    !!reason &&
    linesToReturn.length > 0 &&
    linesToReturn.every((l) => Number(l.returned_qty) > 0 && l.price !== "") &&
    !createMutation.isPending;

  return (
    <div className="max-w-3xl space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/sales/returns")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{t("sales.returns.new")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>{t("sales.quotations.customer")}</Label>
            <Select
              value={partnerId}
              onValueChange={(v) => {
                setPartnerId(v ?? "");
                setInvoiceId("");
                setReturnLines([]);
                setLoadedInvoiceId(null);
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("sales.quotations.select_customer")}>
                  {(value: string) => {
                    const partner = partnersQuery.data?.find((p) => p.id === value);
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
                {partnersQuery.data?.map((p) => (
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
            <Label>{t("sales.returns.select_invoice")}</Label>
            <Select value={invoiceId} onValueChange={(v) => setInvoiceId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("sales.returns.select_invoice")}>
                  {(value: string) => {
                    const invoice = returnableInvoices.find((i) => i.id === value);
                    return invoice ? `${invoice.number} — ${formatCurrency(invoice.total_amount)}` : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {returnableInvoices.map((invoice) => (
                  <SelectItem key={invoice.id} value={invoice.id}>
                    {invoice.number} — {formatCurrency(invoice.total_amount)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {invoiceId && invoiceDetailQuery.isLoading && (
            <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
          )}

          {returnLines.length > 0 && (
            <div className="space-y-2">
              <Label>{t("sales.returns.lines_title")}</Label>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("sales.quotations.select_product")}</TableHead>
                    <TableHead className="text-end">{t("sales.returns.original_qty")}</TableHead>
                    <TableHead className="text-end">{t("sales.returns.original_price")}</TableHead>
                    <TableHead className="text-end w-28">{t("sales.returns.returned_qty")}</TableHead>
                    <TableHead className="text-end w-28">{t("sales.returns.return_price")}</TableHead>
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
            <Label>{t("sales.returns.reason")}</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("sales.returns.reason")} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={restock} onChange={(e) => setRestock(e.target.checked)} />
            {t("sales.invoice.restock_label")}
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!canSubmit}
          >
            {createMutation.isPending ? t("common.loading") : t("sales.returns.new")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
