"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { EntitySearchSelect } from "@/components/erp/entity-search-select/entity-search-select";
import { Can } from "@/components/erp/permissions/can";
import { StockBalanceHint } from "@/components/erp/stock-balance-hint/stock-balance-hint";
import { PermissionDenied } from "@/components/erp/states/permission-denied";
import { ReportView } from "@/components/erp/report-view/report-view";
import { ReportPrintHeader } from "@/components/erp/report-view/report-print-header";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { reportingApi } from "@/features/reporting/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { reportExportHandlers } from "@/lib/report-export";
import { sourceDocumentHref, sourceDocumentLabelKey } from "@/lib/source-document-links";
import { statusVariant } from "@/lib/status-variant";
import { toastError, toastSuccess } from "@/lib/toast";
import type { CycleCount, LowStockRow, StockMove, StockQuant, Warehouse } from "@/features/inventory/api/types";
import Link from "next/link";

const CARDEX_SOURCE_TABLES = [
  "sales_invoice",
  "goods_receipt",
  "manual_receipt",
  "stock_transfer",
  "cycle_count_line",
] as const;

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
      sortable: true,
      sortValue: (r) => (r.is_default ? 1 : 0),
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
                <EntitySearchSelect
                  items={products.map((p) => ({
                    id: p.id,
                    label: p.name,
                    code: p.sku,
                    searchText: `${p.sku} ${p.name} ${p.name_ar ?? ""}`,
                  }))}
                  value={productId || null}
                  onChange={(v) => setProductId(v ?? "")}
                  placeholder={t("inventory.stock.product")}
                />
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
    {
      key: "move_type",
      header: t("inventory.moves.type"),
      sortable: true,
      sortValue: (r) => r.move_type,
      render: (r) => <Badge variant="secondary">{r.move_type}</Badge>,
    },
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
      sortable: true,
      sortValue: (r) => {
        const labelKey = sourceDocumentLabelKey(r.source_table);
        return labelKey ? t(labelKey) : r.source_table;
      },
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
  const { products } = useProductLabel();

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
              <EntitySearchSelect
                items={products.map((p) => ({
                  id: p.id,
                  label: p.name,
                  code: p.sku,
                  searchText: `${p.sku} ${p.name} ${p.name_ar ?? ""}`,
                }))}
                value={productId || null}
                onChange={(v) => setProductId(v ?? "")}
                placeholder={t("inventory.stock.product")}
              />
              <StockBalanceHint companyId={companyId} productId={productId} warehouseId={sourceWarehouseId} />
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
    {
      key: "status",
      header: t("purchasing.orders.status"),
      sortable: true,
      sortValue: (r) => r.status,
      render: (r) => <Badge variant={statusVariant(r.status)}>{r.status}</Badge>,
    },
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

function CardexTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { products, label: productLabel } = useProductLabel();
  const { warehouses, label: warehouseLabel } = useWarehouseLabel();

  const [productId, setProductId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [sourceTable, setSourceTable] = useState("");
  const [dateFrom, setDateFrom] = useState(() => new Date().toISOString().slice(0, 8) + "01");
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [ranAt, setRanAt] = useState<{ productId: string; from: string; to: string; warehouseId: string; sourceTable: string } | null>(
    null
  );

  const cardexQuery = useQuery({
    queryKey: ["stock-cardex", companyId, ranAt],
    queryFn: () =>
      inventoryApi.getProductCardex(companyId, {
        productId: ranAt!.productId,
        dateFrom: ranAt!.from,
        dateTo: ranAt!.to,
        warehouseId: ranAt!.warehouseId || undefined,
        sourceTable: ranAt!.sourceTable || undefined,
      }),
    enabled: !!ranAt,
  });

  const cardexProduct = ranAt ? products.find((p) => p.id === ranAt.productId) : undefined;

  return (
    <ReportView
      title={t("inventory.cardex.title")}
      filterArea={
        <div className="flex flex-wrap gap-4">
          <div className="flex flex-col gap-1">
            <Label className="text-xs">{t("inventory.stock.product")}</Label>
            <EntitySearchSelect
              items={products.map((p) => ({
                id: p.id,
                label: p.name,
                code: p.sku,
                searchText: `${p.sku} ${p.name} ${p.name_ar ?? ""}`,
              }))}
              value={productId || null}
              onChange={(v) => setProductId(v ?? "")}
              placeholder={t("inventory.stock.product")}
              className="w-48"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">{t("inventory.cardex.date_from")}</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">{t("inventory.cardex.date_to")}</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">{t("inventory.stock.warehouse")}</Label>
            <Select value={warehouseId || "all"} onValueChange={(v) => setWarehouseId(v === "all" ? "" : (v ?? ""))}>
              <SelectTrigger className="w-44">
                <SelectValue placeholder={t("inventory.cardex.all_warehouses")}>
                  {(value: string) => (value === "all" ? t("inventory.cardex.all_warehouses") : warehouseLabel(value))}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("inventory.cardex.all_warehouses")}</SelectItem>
                {warehouses.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">{t("inventory.cardex.document_type")}</Label>
            <Select value={sourceTable || "all"} onValueChange={(v) => setSourceTable(v === "all" ? "" : (v ?? ""))}>
              <SelectTrigger className="w-44">
                <SelectValue placeholder={t("inventory.cardex.all_types")}>
                  {(value: string) => {
                    if (value === "all") return t("inventory.cardex.all_types");
                    const key = sourceDocumentLabelKey(value);
                    return key ? t(key) : value;
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("inventory.cardex.all_types")}</SelectItem>
                {CARDEX_SOURCE_TABLES.map((st) => {
                  const key = sourceDocumentLabelKey(st);
                  return (
                    <SelectItem key={st} value={st}>
                      {key ? t(key) : st}
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>
        </div>
      }
      onApply={() => setRanAt({ productId, from: dateFrom, to: dateTo, warehouseId, sourceTable })}
      onPrint={ranAt && cardexQuery.data ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/inventory/stock/cardex",
            {
              product_id: ranAt.productId,
              date_from: ranAt.from,
              date_to: ranAt.to,
              warehouse_id: ranAt.warehouseId || undefined,
              source_table: ranAt.sourceTable || undefined,
              lang: locale,
            },
            companyId
          )
        : {})}
      isLoading={cardexQuery.isLoading}
      isError={cardexQuery.isError}
      errorMessage={cardexQuery.error instanceof ApiError ? cardexQuery.error.detail : undefined}
      onRetry={() => cardexQuery.refetch()}
      isEmpty={!!ranAt && !!cardexQuery.data && cardexQuery.data.lines.length === 0}
      kpis={
        cardexQuery.data
          ? [
              { label: t("inventory.cardex.opening_qty"), value: cardexQuery.data.opening_qty },
              { label: t("inventory.cardex.closing_qty"), value: cardexQuery.data.closing_qty },
            ]
          : undefined
      }
    >
      {!ranAt && <p className="text-sm text-muted-foreground">{t("inventory.cardex.select_product_hint")}</p>}
      {ranAt && cardexQuery.data && (
        <>
          <ReportPrintHeader reportTitle={t("inventory.cardex.title")} dateRangeLabel={`${ranAt.from} – ${ranAt.to}`} />
          <div className="flex items-center gap-3">
            <EntityImage src={cardexProduct?.image_path} name={productLabel(ranAt.productId)} size="lg" shape="square" />
            <h2 className="text-lg font-semibold">{productLabel(ranAt.productId)}</h2>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("inventory.moves.date")}</TableHead>
                <TableHead>{t("inventory.moves.type")}</TableHead>
                <TableHead>{t("inventory.moves.source")}</TableHead>
                <TableHead className="text-end">{t("inventory.moves.qty")}</TableHead>
                <TableHead className="text-end">{t("inventory.moves.unit_cost")}</TableHead>
                <TableHead className="text-end">{t("inventory.cardex.running_qty")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow className="text-muted-foreground">
                <TableCell colSpan={5} className="italic">
                  {t("inventory.cardex.opening_qty")}
                </TableCell>
                <TableCell className="text-end font-mono">{cardexQuery.data.opening_qty}</TableCell>
              </TableRow>
              {cardexQuery.data.lines.map((line) => {
                const href = sourceDocumentHref(line.source_table, line.source_id);
                const labelKey = sourceDocumentLabelKey(line.source_table);
                const label = labelKey ? t(labelKey) : line.source_table;
                return (
                  <TableRow key={line.id}>
                    <TableCell>{formatDate(line.moved_at, locale)}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{line.move_type}</Badge>
                    </TableCell>
                    <TableCell>
                      {href ? (
                        <Link href={href} className="underline-offset-4 hover:underline">
                          {label}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">{label}</span>
                      )}
                    </TableCell>
                    <TableCell className={`text-end font-mono ${Number(line.signed_qty) < 0 ? "text-destructive" : ""}`}>
                      {Number(line.signed_qty) > 0 ? `+${line.signed_qty}` : line.signed_qty}
                    </TableCell>
                    <TableCell className="text-end">{formatCurrency(line.unit_cost)}</TableCell>
                    <TableCell className="text-end font-mono font-semibold">{line.running_qty}</TableCell>
                  </TableRow>
                );
              })}
              <TableRow className="font-semibold border-t-2">
                <TableCell colSpan={5}>{t("inventory.cardex.closing_qty")}</TableCell>
                <TableCell className="text-end font-mono">{cardexQuery.data.closing_qty}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </>
      )}
    </ReportView>
  );
}

function LowStockTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const lowStockQuery = useQuery({
    queryKey: ["low-stock", companyId],
    queryFn: () => inventoryApi.listLowStock(companyId),
  });

  const columns: ERPColumn<LowStockRow>[] = [
    {
      key: "sku",
      header: t("inventory.low_stock.sku"),
      sortable: true,
      sortValue: (r) => r.sku,
      render: (r) => (
        <Link href={`/inventory/stock-card/${r.product_id}`} className="font-medium underline-offset-4 hover:underline">
          {r.sku}
        </Link>
      ),
    },
    {
      key: "name",
      header: t("inventory.low_stock.product"),
      sortable: true,
      sortValue: (r) => (locale === "ar" && r.name_ar ? r.name_ar : r.name),
      render: (r) => (locale === "ar" && r.name_ar ? r.name_ar : r.name),
    },
    {
      key: "qty_on_hand",
      header: t("inventory.low_stock.qty_on_hand"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.qty_on_hand),
      render: (r) => r.qty_on_hand,
    },
    {
      key: "reorder_point",
      header: t("inventory.low_stock.reorder_point"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.reorder_point),
      render: (r) => r.reorder_point,
    },
    {
      key: "shortfall",
      header: t("inventory.low_stock.shortfall"),
      align: "end",
      sortable: true,
      sortValue: (r) => Number(r.shortfall),
      render: (r) => <Badge variant="destructive">{r.shortfall}</Badge>,
    },
  ];

  return (
    <ERPListView
      title={t("inventory.tabs.low_stock")}
      columns={columns}
      rows={lowStockQuery.data}
      rowKey={(r) => r.product_id}
      getRowHref={(r) => `/inventory/stock-card/${r.product_id}`}
      isLoading={lowStockQuery.isLoading}
      isError={lowStockQuery.isError}
      errorMessage={lowStockQuery.error instanceof ApiError ? lowStockQuery.error.detail : undefined}
      onRetry={() => lowStockQuery.refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["low-stock", companyId] })}
      searchText={(r) => `${r.sku} ${r.name} ${r.name_ar ?? ""}`}
      searchPlaceholder={t("list.search_placeholder")}
      emptyDescription={t("inventory.low_stock.empty_description")}
    />
  );
}

function ValuationTab() {
  const { t, locale } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { warehouses } = useWarehouseLabel();

  const [warehouseId, setWarehouseId] = useState("");
  const [ranAt, setRanAt] = useState<{ warehouseId: string } | null>({ warehouseId: "" });

  const valuationQuery = useQuery({
    queryKey: ["inventory-valuation", companyId, ranAt?.warehouseId],
    queryFn: () => reportingApi.inventoryValuation(companyId, ranAt!.warehouseId || undefined),
    enabled: !!ranAt,
  });

  const rows = valuationQuery.data ?? [];
  const totalValue = rows.reduce((sum, r) => sum + Number(r.total_value), 0);

  return (
    <ReportView
      title={t("inventory.tabs.valuation")}
      filterArea={
        <div className="flex flex-col gap-1">
          <Label className="text-xs">{t("inventory.stock.warehouse")}</Label>
          <Select value={warehouseId || "all"} onValueChange={(v) => setWarehouseId(v === "all" ? "" : (v ?? ""))}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder={t("inventory.cardex.all_warehouses")}>
                {(value: string) =>
                  value === "all"
                    ? t("inventory.cardex.all_warehouses")
                    : (warehouses.find((w) => w.id === value)?.name ?? value)
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("inventory.cardex.all_warehouses")}</SelectItem>
              {warehouses.map((w) => (
                <SelectItem key={w.id} value={w.id}>
                  {w.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      }
      onApply={() => setRanAt({ warehouseId })}
      onPrint={ranAt && rows.length > 0 ? () => window.print() : undefined}
      {...(ranAt
        ? reportExportHandlers(
            "/api/v1/reporting/inventory-valuation",
            { warehouse_id: ranAt.warehouseId || undefined, lang: locale },
            companyId
          )
        : {})}
      isLoading={valuationQuery.isLoading}
      isError={valuationQuery.isError}
      errorMessage={valuationQuery.error instanceof ApiError ? valuationQuery.error.detail : undefined}
      onRetry={() => valuationQuery.refetch()}
      isEmpty={!!ranAt && !valuationQuery.isLoading && rows.length === 0}
      kpis={
        rows.length > 0
          ? [
              { label: t("inventory.valuation.products"), value: String(rows.length) },
              { label: t("inventory.valuation.total_value"), value: formatCurrency(totalValue) },
            ]
          : undefined
      }
    >
      {ranAt && rows.length > 0 && (
        <>
          <ReportPrintHeader reportTitle={t("inventory.tabs.valuation")} />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("inventory.stock.warehouse")}</TableHead>
                <TableHead>{t("inventory.stock.product")}</TableHead>
                <TableHead className="text-end">{t("inventory.stock.qty_on_hand")}</TableHead>
                <TableHead className="text-end">{t("inventory.valuation.unit_cost")}</TableHead>
                <TableHead className="text-end font-semibold">{t("inventory.valuation.total_value")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={`${r.product_id}-${r.warehouse_id}`}>
                  <TableCell>{r.warehouse_name}</TableCell>
                  <TableCell>
                    <Link href={`/inventory/stock-card/${r.product_id}`} className="underline-offset-4 hover:underline">
                      {r.product_code} — {r.product_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-end tabular-nums">{r.qty_on_hand}</TableCell>
                  <TableCell className="text-end tabular-nums">{formatCurrency(r.unit_cost)}</TableCell>
                  <TableCell className="text-end tabular-nums font-semibold">{formatCurrency(r.total_value)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell colSpan={4} className="font-bold">
                  {t("inventory.valuation.total_value")}
                </TableCell>
                <TableCell className="text-end font-bold tabular-nums">{formatCurrency(totalValue)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </>
      )}
    </ReportView>
  );
}

function InventoryReconciliationTab() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const reconQuery = useQuery({
    queryKey: ["inventory-reconciliation", companyId],
    queryFn: () => reportingApi.inventoryReconciliation(companyId),
  });
  const r = reconQuery.data;

  return (
    <ReportView
      title={t("inventory.reconciliation.title")}
      isLoading={reconQuery.isLoading}
      isError={reconQuery.isError}
      errorMessage={reconQuery.error instanceof ApiError ? reconQuery.error.detail : undefined}
      onRetry={() => reconQuery.refetch()}
      kpis={
        r
          ? [
              { label: t("inventory.reconciliation.gl_balance"), value: formatCurrency(r.gl_balance) },
              { label: t("inventory.reconciliation.valuation_total"), value: formatCurrency(r.valuation_total) },
              { label: t("inventory.reconciliation.difference"), value: formatCurrency(r.difference) },
            ]
          : undefined
      }
    >
      {r && (
        <>
          <p className="mb-4 text-sm text-muted-foreground">{t("inventory.reconciliation.hint")}</p>
          <div className="flex items-center gap-3">
            <Badge variant={r.matched ? "default" : "destructive"} className="text-sm">
              {r.matched ? t("inventory.reconciliation.matched") : t("inventory.reconciliation.mismatched")}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {t("inventory.reconciliation.tolerance")}: {formatCurrency(r.tolerance)}
            </span>
          </div>
        </>
      )}
    </ReportView>
  );
}

export default function InventoryPage() {
  const searchParams = useSearchParams();
  // See the same note in accounting/page.tsx — Base UI's Tabs.Panel doesn't
  // reliably hide inactive panels once a second one mounts, so the active
  // tab is tracked ourselves and gates each panel's content directly.
  const urlTab = searchParams.get("tab");
  const [tab, setTab] = useState(() => urlTab ?? "warehouses");
  // Same deep-link sync as accounting/page.tsx: the sidebar's new
  // Inventory sub-links (?tab=stock, ?tab=moves, ...) are same-route
  // client-side navigations, so this component never remounts and the
  // useState initializer above only ever runs once.
  const [lastUrlTab, setLastUrlTab] = useState(urlTab);
  if (urlTab && urlTab !== lastUrlTab) {
    setLastUrlTab(urlTab);
    setTab(urlTab);
  }
  // Owner-requested: the sidebar's "Inventory" group now lists every
  // screen directly (nav-config.ts), so picking one should land on that
  // screen alone — not also show all 8 tab names as one horizontal row.
  return (
    <div className="space-y-6">
      {tab === "warehouses" && <WarehousesTab />}
      {tab === "stock" && <StockTab />}
      {tab === "moves" && <MovesTab />}
      {tab === "transfer" && <TransferTab />}
      {tab === "cycle-counts" && <CycleCountsTab />}
      {tab === "cardex" && <CardexTab />}
      {tab === "valuation" && <ValuationTab />}
      {tab === "inventory-reconciliation" && <InventoryReconciliationTab />}
      {tab === "low-stock" && <LowStockTab />}
    </div>
  );
}
