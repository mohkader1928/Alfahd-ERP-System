"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { toastError, toastSuccess } from "@/lib/toast";

function useProductLabel() {
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const productsQuery = useQuery({
    queryKey: ["products", companyId],
    queryFn: () => identityApi.listProducts(companyId, branchId),
  });
  return {
    products: productsQuery.data ?? [],
    label: (productId: string) => productsQuery.data?.find((p) => p.id === productId)?.name ?? productId,
  };
}

function WarehousesTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });

  const createMutation = useMutation({
    mutationFn: () => inventoryApi.createWarehouse(companyId, branchId, { name, is_default: isDefault }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["warehouses", companyId] });
      toastSuccess(t("toast.success_title"), name);
      setName("");
      setIsDefault(false);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("inventory.tabs.warehouses")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">{t("inventory.warehouses.name")}</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
          </div>
          <label className="flex items-center gap-1 text-sm">
            <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
            {t("inventory.warehouses.default")}
          </label>
          <Button
            size="sm"
            onClick={() => {
              setError(null);
              createMutation.mutate();
            }}
            disabled={!name || createMutation.isPending}
          >
            <Plus className="h-4 w-4" />
            {t("inventory.warehouses.save")}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("inventory.warehouses.name")}</TableHead>
              <TableHead>{t("inventory.warehouses.default")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!warehousesQuery.isLoading && warehousesQuery.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={2} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {warehousesQuery.data?.map((w) => (
              <TableRow key={w.id}>
                <TableCell>{w.name}</TableCell>
                <TableCell>{w.is_default && <Badge>{t("inventory.warehouses.default")}</Badge>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function useWarehouseLocations(warehouseId: string) {
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  return useQuery({
    queryKey: ["locations", companyId, warehouseId],
    queryFn: () => inventoryApi.listLocations(companyId, warehouseId),
    enabled: !!warehouseId,
  });
}

function StockTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const { products, label: productLabel } = useProductLabel();

  const [productId, setProductId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [qty, setQty] = useState("1");
  const [unitCost, setUnitCost] = useState("0");
  const [error, setError] = useState<string | null>(null);

  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });
  const locationsQuery = useWarehouseLocations(warehouseId);
  const quantsQuery = useQuery({
    queryKey: ["stock-quants", companyId],
    queryFn: () => inventoryApi.listStockQuants(companyId),
  });

  const receiveMutation = useMutation({
    mutationFn: () =>
      inventoryApi.receiveStock(companyId, {
        product_id: productId,
        location_id: locationsQuery.data![0].id,
        qty,
        unit_cost: unitCost,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stock-quants", companyId] });
      queryClient.invalidateQueries({ queryKey: ["stock-moves", companyId] });
      toastSuccess(t("toast.success_title"), t("inventory.stock.receive"));
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("inventory.tabs.stock")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2 rounded-md border p-3">
          <div className="w-48 space-y-1">
            <Label className="text-xs">{t("inventory.stock.product")}</Label>
            <Select value={productId} onValueChange={(v) => setProductId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("inventory.stock.product")}>
                  {(value: string) => productLabel(value)}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {products.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-48 space-y-1">
            <Label className="text-xs">{t("inventory.stock.warehouse")}</Label>
            <Select value={warehouseId} onValueChange={(v) => setWarehouseId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("inventory.stock.warehouse")}>
                  {(value: string) => warehousesQuery.data?.find((w) => w.id === value)?.name ?? value}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {warehousesQuery.data?.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-24 space-y-1">
            <Label className="text-xs">{t("inventory.stock.qty_on_hand")}</Label>
            <Input value={qty} onChange={(e) => setQty(e.target.value)} />
          </div>
          <div className="w-28 space-y-1">
            <Label className="text-xs">{t("inventory.stock.unit_cost")}</Label>
            <Input value={unitCost} onChange={(e) => setUnitCost(e.target.value)} />
          </div>
          <Button
            size="sm"
            onClick={() => {
              setError(null);
              receiveMutation.mutate();
            }}
            disabled={!productId || !locationsQuery.data?.length || receiveMutation.isPending}
          >
            {receiveMutation.isPending ? t("common.loading") : t("inventory.stock.receive")}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("inventory.stock.product")}</TableHead>
              <TableHead className="text-end">{t("inventory.stock.qty_on_hand")}</TableHead>
              <TableHead className="text-end">{t("inventory.stock.avg_cost")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!quantsQuery.isLoading && quantsQuery.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {quantsQuery.data?.map((q) => (
              <TableRow key={`${q.product_id}-${q.location_id}`}>
                <TableCell>{productLabel(q.product_id)}</TableCell>
                <TableCell className="text-end">{q.qty_on_hand}</TableCell>
                <TableCell className="text-end">{formatCurrency(q.moving_avg_cost)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function MovesTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { label: productLabel } = useProductLabel();

  const movesQuery = useQuery({
    queryKey: ["stock-moves", companyId],
    queryFn: () => inventoryApi.listStockMoves(companyId),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("inventory.tabs.moves")}</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("inventory.stock.product")}</TableHead>
              <TableHead>{t("inventory.moves.type")}</TableHead>
              <TableHead className="text-end">{t("inventory.moves.qty")}</TableHead>
              <TableHead className="text-end">{t("inventory.moves.unit_cost")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!movesQuery.isLoading && movesQuery.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  {t("common.empty")}
                </TableCell>
              </TableRow>
            )}
            {movesQuery.data?.map((m) => (
              <TableRow key={m.id}>
                <TableCell>{productLabel(m.product_id)}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{m.move_type}</Badge>
                </TableCell>
                <TableCell className="text-end">{m.qty}</TableCell>
                <TableCell className="text-end">{formatCurrency(m.unit_cost)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function TransferTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const { products, label: productLabel } = useProductLabel();

  const [productId, setProductId] = useState("");
  const [sourceWarehouseId, setSourceWarehouseId] = useState("");
  const [destWarehouseId, setDestWarehouseId] = useState("");
  const [qty, setQty] = useState("1");
  const [error, setError] = useState<string | null>(null);

  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });
  const sourceLocationsQuery = useWarehouseLocations(sourceWarehouseId);
  const destLocationsQuery = useWarehouseLocations(destWarehouseId);

  const transferMutation = useMutation({
    mutationFn: () =>
      inventoryApi.createTransfer(companyId, {
        product_id: productId,
        source_location_id: sourceLocationsQuery.data![0].id,
        dest_location_id: destLocationsQuery.data![0].id,
        qty,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stock-quants", companyId] });
      queryClient.invalidateQueries({ queryKey: ["stock-moves", companyId] });
      toastSuccess(t("toast.success_title"), t("inventory.transfer.save"));
      setQty("1");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("inventory.transfer.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-48 space-y-1">
            <Label className="text-xs">{t("inventory.stock.product")}</Label>
            <Select value={productId} onValueChange={(v) => setProductId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("inventory.stock.product")}>
                  {(value: string) => productLabel(value)}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {products.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-44 space-y-1">
            <Label className="text-xs">{t("inventory.transfer.source")}</Label>
            <Select value={sourceWarehouseId} onValueChange={(v) => setSourceWarehouseId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("inventory.transfer.source")}>
                  {(value: string) => warehousesQuery.data?.find((w) => w.id === value)?.name ?? value}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {warehousesQuery.data?.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-44 space-y-1">
            <Label className="text-xs">{t("inventory.transfer.dest")}</Label>
            <Select value={destWarehouseId} onValueChange={(v) => setDestWarehouseId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("inventory.transfer.dest")}>
                  {(value: string) => warehousesQuery.data?.find((w) => w.id === value)?.name ?? value}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {warehousesQuery.data?.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-24 space-y-1">
            <Label className="text-xs">{t("inventory.transfer.qty")}</Label>
            <Input value={qty} onChange={(e) => setQty(e.target.value)} />
          </div>
          <Button
            size="sm"
            onClick={() => {
              setError(null);
              transferMutation.mutate();
            }}
            disabled={
              !productId ||
              !sourceLocationsQuery.data?.length ||
              !destLocationsQuery.data?.length ||
              sourceWarehouseId === destWarehouseId ||
              transferMutation.isPending
            }
          >
            {transferMutation.isPending ? t("common.loading") : t("inventory.transfer.save")}
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

export default function InventoryPage() {
  const { t } = useI18n();
  // See the same note in accounting/page.tsx — Base UI's Tabs.Panel doesn't
  // reliably hide inactive panels once a second one mounts, so the active
  // tab is tracked ourselves and gates each panel's content directly.
  const [tab, setTab] = useState("warehouses");
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t("nav.inventory")}</h1>
      <Tabs value={tab} onValueChange={(v) => setTab(v as string)}>
        <TabsList>
          <TabsTrigger value="warehouses">{t("inventory.tabs.warehouses")}</TabsTrigger>
          <TabsTrigger value="stock">{t("inventory.tabs.stock")}</TabsTrigger>
          <TabsTrigger value="moves">{t("inventory.tabs.moves")}</TabsTrigger>
          <TabsTrigger value="transfer">{t("inventory.tabs.transfer")}</TabsTrigger>
        </TabsList>
        <TabsContent value="warehouses">{tab === "warehouses" && <WarehousesTab />}</TabsContent>
        <TabsContent value="stock">{tab === "stock" && <StockTab />}</TabsContent>
        <TabsContent value="moves">{tab === "moves" && <MovesTab />}</TabsContent>
        <TabsContent value="transfer">{tab === "transfer" && <TransferTab />}</TabsContent>
      </Tabs>
    </div>
  );
}
