"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";

function PartnersSection() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [isCustomer, setIsCustomer] = useState(true);
  const [isVendor, setIsVendor] = useState(false);
  const [vatNumber, setVatNumber] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: partners, isLoading } = useQuery({
    queryKey: ["partners", companyId],
    queryFn: () => identityApi.listPartners(companyId, branchId),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      identityApi.createPartner(companyId, branchId, {
        name,
        is_customer: isCustomer,
        is_vendor: isVendor,
        vat_number: vatNumber || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["partners", companyId] });
      setName("");
      setVatNumber("");
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Customers &amp; Vendors</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">VAT number (leave empty for B2C)</Label>
            <Input value={vatNumber} onChange={(e) => setVatNumber(e.target.value)} maxLength={15} className="w-48" />
          </div>
          <label className="flex items-center gap-1 text-sm">
            <input type="checkbox" checked={isCustomer} onChange={(e) => setIsCustomer(e.target.checked)} />
            Customer
          </label>
          <label className="flex items-center gap-1 text-sm">
            <input type="checkbox" checked={isVendor} onChange={(e) => setIsVendor(e.target.checked)} />
            Vendor
          </label>
          <Button
            size="sm"
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!name || (!isCustomer && !isVendor) || createMutation.isPending}
          >
            {t("common.save")}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>VAT #</TableHead>
              <TableHead>Type</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!isLoading && partners?.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {partners?.map((p) => (
              <TableRow key={p.id}>
                <TableCell>{p.name}</TableCell>
                <TableCell>{p.vat_number ?? "—"}</TableCell>
                <TableCell className="space-x-1">
                  {p.is_customer && <Badge variant="secondary">Customer</Badge>}
                  {p.is_vendor && <Badge variant="outline">Vendor</Badge>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function ProductsSection() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const queryClient = useQueryClient();

  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("0.00");
  const [error, setError] = useState<string | null>(null);

  const { data: products, isLoading } = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });

  const createMutation = useMutation({
    mutationFn: () => identityApi.createProduct(companyId, branchId, { sku, name, sales_price: price }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products", companyId] });
      setSku("");
      setName("");
      setPrice("0.00");
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Products</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">SKU</Label>
            <Input value={sku} onChange={(e) => setSku(e.target.value)} className="w-32" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Sales price</Label>
            <Input value={price} onChange={(e) => setPrice(e.target.value)} className="w-28" />
          </div>
          <Button
            size="sm"
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!sku || !name || createMutation.isPending}
          >
            {t("common.save")}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>SKU</TableHead>
              <TableHead>Name</TableHead>
              <TableHead className="text-end">Price</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!isLoading && products?.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {products?.map((p) => (
              <TableRow key={p.id}>
                <TableCell>{p.sku}</TableCell>
                <TableCell>{p.name}</TableCell>
                <TableCell className="text-end">{p.sales_price}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export default function AdminPage() {
  const { t } = useI18n();
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t("nav.admin")}</h1>
      <PartnersSection />
      <ProductsSection />
    </div>
  );
}
