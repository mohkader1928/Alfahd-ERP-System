"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { Can } from "@/components/erp/permissions/can";
import { PermissionDenied } from "@/components/erp/states/permission-denied";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { sourceDocumentHref, sourceDocumentLabelKey } from "@/lib/source-document-links";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";
import type { CycleCount, StockMove, StockQuant, Warehouse } from "@/features/inventory/api/types";
import Link from "next/link";

/**
 * Bundle 3 — Purchasing/Inventory List Consistency. All four tabs move
 * onto the same `ERPListView` every other list screen in the app uses
 * (search, sort, pagination, shared empty/error states) instead of a
 * hand-rolled <Table>. The three inline quick-create forms (Warehouse,
 * Receive Stock, Transfer) deliberately stay inline rather than becoming
 * full FormView pages — that would add clicks for no UX benefit, the
 * opposite of the "minimum clicks" standard this project holds itself to
 * — but each is now gated behind `<Can>`, same as every other mutating
 * action in the app.
 */
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

  const setDefaultMutation = useMutation({
    mutationFn: (warehouseId: string) => inventoryApi.setDefaultWarehouse(companyId, warehouseId),
    onSuccess: (warehouse) => {
      queryClient.invalidateQueries({ queryKey: ["warehouses", companyId] });
      toastSuccess(t("toast.success_title"), warehouse.name);
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const columns: ERPColumn<Warehouse>[] = [
    { key: "name", header: t("inventory.warehouses.name"), sortable: true, sortValue: (r) => r.name, render: (r) => r.name },
    {
      key: "is_default",
      header: t("inventory.warehouses.default"),
      render: (r) => (r.is_default ? <Badge>{t("inventory.warehouses.default")}</Badge> : "—"),
    },
  ];

  return (
    <div className="space-y-4">
      <Can permission="inventory.warehouse.manage">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("inventory.warehouses.create_title")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label className="text-xs">{t("inventory.warehouses.name")}</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} className="w-48" />
              </div>
              <label className="flex h-8 items-center gap-1 text-sm">
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
                {createMutation.isPending ? t("common.loading") : t("inventory.warehouses.save")}
              </Button>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </Can>

      <ERPListView
        title={t("inventory.tabs.warehouses")}
        columns={columns}
        rows={warehousesQuery.data}
        rowKey={(r) => r.id}
        isLoading={warehousesQuery.isLoading}
        isError={warehousesQuery.isError}
        errorMessage={warehousesQuery.error instanceof ApiError ? warehousesQuery.error.detail : undefined}
        onRetry={() => warehousesQuery.refetch()}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["warehouses", companyId] })}
        searchText={(r) => r.name}
        searchPlaceholder={t("list.search_placeholder")}
        emptyDescription={t("inventory.warehouses.empty_description")}
        rowActions={(r) =>
          !r.is_default && (
            <Can permission="inventory.warehouse.manage">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setDefaultMutation.mutate(r.id)}
                disabled={setDefaultMutation.isPending}
              >
                {t("inventory.warehouses.set_default")}
              </Button>
            </Can>
          )
        }
      />
    </div>
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

  const columns: ERPColumn<StockQuant>[] = [
    { key: "product", header: t("inventory.stock.product"), sortable: true, sortValue: (r) => productLabel(r.product_id), render: (r) => productLabel(r.product_id) },
    {
      key: "qty_on_hand",
      header: t("inventory.stock.qty_on_hand"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.qty_on_hand),
      render: (r) => r.qty_on_hand,
    },
    {
      key: "moving_avg_cost",
      header: t("inventory.stock.avg_cost"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.moving_avg_cost),
      render: (r) => formatCurrency(r.moving_avg_cost),
    },
  ];

  return (
    <div className="space-y-4">
      <Can permission="inventory.stock.receive">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("inventory.stock.receive_title")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="w-48 space-y-1">
                <Label className="text-xs">{t("inventory.stock.product")}</Label>
                <Select value={productId} onValueChange={(v) => setProductId(v ?? "")}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={t("inventory.stock.product")}>{(value: string) => productLabel(value)}</SelectValue>
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
          </CardContent>
        </Card>
      </Can>

      <ERPListView
        title={t("inventory.tabs.stock")}
        columns={columns}
        rows={quantsQuery.data}
        rowKey={(r) => `${r.product_id}-${r.location_id}`}
        isLoading={quantsQuery.isLoading}
        isError={quantsQuery.isError}
        errorMessage={quantsQuery.error instanceof ApiError ? quantsQuery.error.detail : undefined}
        onRetry={() => quantsQuery.refetch()}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["stock-quants", companyId] })}
        searchText={(r) => productLabel(r.product_id)}
        searchPlaceholder={t("list.search_placeholder")}
        emptyDescription={t("inventory.stock.empty_description")}
        getRowHref={(r) => `/inventory/stock-card/${r.product_id}`}
      />
    </div>
  );
}

function MovesTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const { label: productLabel } = useProductLabel();

  const movesQuery = useQuery({
    queryKey: ["stock-moves", companyId],
    queryFn: () => inventoryApi.listStockMoves(companyId),
  });

  const columns: ERPColumn<StockMove>[] = [
    {
      key: "moved_at",
      header: t("inventory.moves.date"),
      sortable: true,
      sortValue: (r) => r.moved_at,
      render: (r) => formatDate(r.moved_at, locale),
    },
    { key: "product", header: t("inventory.stock.product"), sortable: true, sortValue: (r) => productLabel(r.product_id), render: (r) => productLabel(r.product_id) },
    { key: "move_type", header: t("inventory.moves.type"), render: (r) => <Badge variant="secondary">{r.move_type}</Badge> },
    { key: "qty", header: t("inventory.moves.qty"), align: "end", sortable: true, sortValue: (r) => Number(r.qty), render: (r) => r.qty },
    {
      key: "unit_cost",
      header: t("inventory.moves.unit_cost"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.unit_cost),
      render: (r) => formatCurrency(r.unit_cost),
    },
    {
      key: "source",
      header: t("inventory.moves.source"),
      render: (r) => {
        const href = sourceDocumentHref(r.source_table, r.source_id);
        const labelKey = sourceDocumentLabelKey(r.source_table);
        const label = labelKey ? t(labelKey) : r.source_table;
        return href ? (
          <Link href={href} className="underline-offset-4 hover:underline">
            {label}
          </Link>
        ) : (
          <span className="text-muted-foreground">{label}</span>
        );
      },
    },
  ];

  return (
    <ERPListView
      title={t("inventory.tabs.moves")}
      columns={columns}
      rows={movesQuery.data}
      rowKey={(r) => r.id}
      isLoading={movesQuery.isLoading}
      isError={movesQuery.isError}
      errorMessage={movesQuery.error instanceof ApiError ? movesQuery.error.detail : undefined}
      onRetry={() => movesQuery.refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["stock-moves", companyId] })}
      searchText={(r) => `${productLabel(r.product_id)} ${r.move_type}`}
      searchPlaceholder={t("list.search_placeholder")}
      emptyDescription={t("inventory.moves.empty_description")}
    />
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
    <Can permission="inventory.transfer.create" fallback={<PermissionDenied />}>
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
                  <SelectValue placeholder={t("inventory.stock.product")}>{(value: string) => productLabel(value)}</SelectValue>
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
    </Can>
  );
}

function useWarehouseLabel() {
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const warehousesQuery = useQuery({
    queryKey: ["warehouses", companyId],
    queryFn: () => inventoryApi.listWarehouses(companyId),
  });
  return {
    warehouses: warehousesQuery.data ?? [],
    label: (warehouseId: string) => warehousesQuery.data?.find((w) => w.id === warehouseId)?.name ?? warehouseId,
  };
}

function CycleCountsTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();
  const { label: warehouseLabel } = useWarehouseLabel();

  const cycleCountsQuery = useQuery({
    queryKey: ["cycle-counts", companyId],
    queryFn: () => inventoryApi.listCycleCounts(companyId),
  });

  const columns: ERPColumn<CycleCount>[] = [
    {
      key: "warehouse",
      header: t("inventory.stock.warehouse"),
      sortable: true,
      sortValue: (r) => warehouseLabel(r.warehouse_id),
      render: (r) => warehouseLabel(r.warehouse_id),
    },
    {
      key: "scheduled_date",
      header: t("inventory.cycle_counts.scheduled_date"),
      sortable: true,
      sortValue: (r) => r.scheduled_date,
      render: (r) => formatDate(r.scheduled_date, locale),
    },
    { key: "status", header: t("purchasing.orders.status"), render: (r) => <Badge variant={statusVariant(r.status)}>{r.status}</Badge> },
  ];

  return (
    <ERPListView
      title={t("inventory.cycle_counts.title")}
      columns={columns}
      rows={cycleCountsQuery.data}
      rowKey={(r) => r.id}
      isLoading={cycleCountsQuery.isLoading}
      isError={cycleCountsQuery.isError}
      errorMessage={cycleCountsQuery.error instanceof ApiError ? cycleCountsQuery.error.detail : undefined}
      onRetry={() => cycleCountsQuery.refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["cycle-counts", companyId] })}
      searchText={(r) => `${warehouseLabel(r.warehouse_id)} ${r.status}`}
      searchPlaceholder={t("list.search_placeholder")}
      emptyDescription={t("inventory.cycle_counts.empty_description")}
      getRowHref={(r) => `/inventory/cycle-counts/${r.id}`}
      createAction={{
        label: t("inventory.cycle_counts.new"),
        href: "/inventory/cycle-counts/new",
        permission: "inventory.cycle_count.manage",
      }}
    />
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
          <TabsTrigger value="cycle-counts">{t("inventory.tabs.cycle_counts")}</TabsTrigger>
        </TabsList>
        <TabsContent value="warehouses">{tab === "warehouses" && <WarehousesTab />}</TabsContent>
        <TabsContent value="stock">{tab === "stock" && <StockTab />}</TabsContent>
        <TabsContent value="moves">{tab === "moves" && <MovesTab />}</TabsContent>
        <TabsContent value="transfer">{tab === "transfer" && <TransferTab />}</TabsContent>
        <TabsContent value="cycle-counts">{tab === "cycle-counts" && <CycleCountsTab />}</TabsContent>
      </Tabs>
    </div>
  );
}
