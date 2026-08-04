"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { FilterBar, type FilterFieldConfig } from "@/components/erp/filter-bar/filter-bar";
import { flattenTree } from "@/components/erp/category-select/category-select";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import type { Product } from "@/features/identity/api/types";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";

export default function ProductsListPage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<Record<string, string>>({});

  const categoriesQuery = useQuery({
    queryKey: ["product-categories", companyId],
    queryFn: () => identityApi.listProductCategories(companyId),
  });
  const categoryNodes = flattenTree(categoriesQuery.data ?? []);
  const categoryPath = (id: string | null) =>
    id ? (categoryNodes.find((n) => n.category.id === id)?.path ?? id) : "—";

  const {
    data: products,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["products", companyId, filters.category_id],
    queryFn: () => identityApi.listProducts(companyId, branchId, { categoryId: filters.category_id || undefined }),
  });

  const filterFields: FilterFieldConfig[] = [
    {
      key: "category_id",
      label: t("master_data.products.category"),
      type: "select",
      options: categoryNodes.map((n) => ({ value: n.category.id, label: n.path })),
      width: "w-56",
    },
  ];

  const columns: ERPColumn<Product>[] = [
    { key: "sku", header: t("master_data.products.sku"), sortable: true, sortValue: (r) => r.sku, render: (r) => <span className="font-mono">{r.sku}</span> },
    {
      key: "name",
      header: t("master_data.products.name"),
      sortable: true,
      sortValue: (r) => r.name,
      render: (r) => (
        <span className="flex items-center gap-2">
          <EntityImage src={r.image_path} name={r.name} shape="square" size="xs" />
          {r.name}
        </span>
      ),
    },
    { key: "name_ar", header: t("master_data.products.name_ar"), render: (r) => r.name_ar ?? "—" },
    { key: "category", header: t("master_data.products.category"), render: (r) => categoryPath(r.category_id) },
    {
      key: "is_stockable",
      header: t("master_data.products.stockable"),
      render: (r) => <Badge variant={r.is_stockable ? "default" : "secondary"}>{r.is_stockable ? t("common.yes") : t("common.no")}</Badge>,
    },
    { key: "sales_price", header: t("master_data.products.sales_price"), align: "end", sortable: true, sortValue: (r) => Number(r.sales_price), render: (r) => formatCurrency(r.sales_price) },
  ];

  return (
    <ERPListView
      title={t("master_data.products.title")}
      breadcrumbs={[{ label: t("nav.master_data") }, { label: t("master_data.products.title") }]}
      columns={columns}
      rows={products}
      rowKey={(r) => r.id}
      isLoading={isLoading || categoriesQuery.isLoading}
      isError={isError}
      errorMessage={error instanceof ApiError ? error.detail : undefined}
      onRetry={() => refetch()}
      onRefresh={() => queryClient.invalidateQueries({ queryKey: ["products", companyId] })}
      searchText={(r) => `${r.sku} ${r.name} ${r.name_ar ?? ""}`}
      searchPlaceholder={t("list.search_placeholder")}
      emptyDescription={t("master_data.products.empty_description")}
      filters={
        <FilterBar
          fields={filterFields}
          values={filters}
          onChange={(key, value) => setFilters((prev) => ({ ...prev, [key]: value }))}
          onClear={() => setFilters({})}
        />
      }
      createAction={{ label: t("master_data.products.new"), href: "/master-data/products/new", permission: "product.create" }}
      rowActions={(r) => (
        <Link href={`/master-data/products/${r.id}`} className="text-sm underline-offset-4 hover:underline">
          {t("common.edit")}
        </Link>
      )}
    />
  );
}
