"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RecordCard } from "@/components/erp/record-card/record-card";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { EntityImageUpload } from "@/components/erp/entity-image/entity-image-upload";
import { Can } from "@/components/erp/permissions/can";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { CategorySelect } from "@/components/erp/category-select/category-select";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ErrorState } from "@/components/erp/states/error-state";
import { NotFoundState } from "@/components/erp/states/not-found";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";
import type { Product, ProductCategory, UnitOfMeasure } from "@/features/identity/api/types";

/**
 * Phase 17B: built on RecordCard with one real "Overview" tab — the future
 * Product Card foundation the Phase 17 blueprint calls for (Inventory/
 * Sales/Purchases/Accounting tabs land only once those phases give them
 * real data to show; adding an empty placeholder tab now would be exactly
 * the "meaningless placeholder" this program has repeatedly ruled out).
 */
export default function ProductDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const productQuery = useQuery({
    queryKey: ["product", companyId, id],
    queryFn: () => identityApi.getProduct(companyId, id),
  });
  const categoriesQuery = useQuery({
    queryKey: ["product-categories", companyId],
    queryFn: () => identityApi.listProductCategories(companyId),
  });
  const uomQuery = useQuery({
    queryKey: ["uom", companyId, "all"],
    queryFn: () => identityApi.listUom(companyId),
  });

  if (productQuery.isError && productQuery.error instanceof ApiError && productQuery.error.status === 404) {
    return <NotFoundState label={t("master_data.products.not_found")} />;
  }
  if (productQuery.isError) {
    return <ErrorState onRetry={() => productQuery.refetch()} />;
  }
  if (productQuery.isLoading || !productQuery.data) {
    return null;
  }

  return (
    <ProductEditForm
      key={productQuery.data.id}
      product={productQuery.data}
      categories={categoriesQuery.data ?? []}
      uom={uomQuery.data ?? []}
      companyId={companyId}
    />
  );
}

function ProductEditForm({
  product,
  categories,
  uom,
  companyId,
}: {
  product: Product;
  categories: ProductCategory[];
  uom: UnitOfMeasure[];
  companyId: string;
}) {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [sku, setSku] = useState(product.sku);
  const [name, setName] = useState(product.name);
  const [nameAr, setNameAr] = useState(product.name_ar ?? "");
  const [categoryId, setCategoryId] = useState<string | null>(product.category_id);
  const [uomId, setUomId] = useState<string | null>(product.uom_id);
  const [isStockable, setIsStockable] = useState(product.is_stockable);
  const [salesPrice, setSalesPrice] = useState(product.sales_price);
  const [costPrice, setCostPrice] = useState(product.cost_price);
  const [error, setError] = useState<string | null>(null);

  const updateMutation = useMutation({
    mutationFn: () =>
      identityApi.updateProduct(companyId, product.id, {
        sku,
        name,
        name_ar: nameAr || null,
        category_id: categoryId,
        uom_id: uomId,
        is_stockable: isStockable,
        sales_price: salesPrice,
        cost_price: costPrice,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["product", companyId, product.id] });
      queryClient.invalidateQueries({ queryKey: ["products", companyId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const invalidateProduct = () => {
    queryClient.invalidateQueries({ queryKey: ["product", companyId, product.id] });
    queryClient.invalidateQueries({ queryKey: ["products", companyId] });
  };

  const uploadImageMutation = useMutation({
    mutationFn: (file: File) => identityApi.uploadProductImage(companyId, product.id, file),
    onSuccess: () => {
      invalidateProduct();
      toastSuccess(t("toast.success_title"), t("media.upload"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  const removeImageMutation = useMutation({
    mutationFn: () => identityApi.deleteProductImage(companyId, product.id),
    onSuccess: () => {
      invalidateProduct();
      toastSuccess(t("toast.success_title"), t("media.remove"));
    },
    onError: (err) => toastError(t("toast.error_title"), err instanceof ApiError ? err.detail : t("common.error")),
  });

  return (
    <RecordCard
      breadcrumbs={[
        { label: t("nav.master_data") },
        { label: t("master_data.products.title"), href: "/master-data/products" },
        { label: product.name },
      ]}
      name={product.name}
      code={product.sku}
      avatar={<EntityImage src={product.image_path} name={product.name} shape="square" size="md" />}
      statusBadge={
        <Badge variant={product.is_stockable ? "default" : "secondary"}>
          {product.is_stockable ? t("master_data.products.stockable") : t("master_data.products.non_stockable")}
        </Badge>
      }
      tabs={[
        {
          key: "overview",
          label: t("master_data.record_card.overview"),
          content: (
            <div className="space-y-4">
              <div className="space-y-1">
                <Label>{t("master_data.products.image")}</Label>
                <Can permission="product.update">
                  <EntityImageUpload
                    src={product.image_path}
                    name={product.name}
                    shape="square"
                    isUploading={uploadImageMutation.isPending}
                    isRemoving={removeImageMutation.isPending}
                    onUpload={(file) => uploadImageMutation.mutate(file)}
                    onRemove={product.image_path ? () => removeImageMutation.mutate() : undefined}
                  />
                </Can>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label>{t("master_data.products.sku")}</Label>
                  <Input value={sku} onChange={(e) => setSku(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label>{t("master_data.products.name")}</Label>
                  <Input value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label>{t("master_data.products.name_ar")}</Label>
                  <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} dir="rtl" />
                </div>
                <div className="space-y-1">
                  <Label>{t("master_data.products.category")}</Label>
                  <CategorySelect categories={categories} value={categoryId} onChange={setCategoryId} />
                </div>
                <div className="space-y-1">
                  <Label>{t("master_data.products.uom")}</Label>
                  <Select value={uomId ?? "__none__"} onValueChange={(v) => setUomId(v === "__none__" ? null : (v ?? null))}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t("master_data.products.uom")}>
                        {(v: string) => (v === "__none__" ? t("master_data.category.none") : (uom.find((u) => u.id === v)?.name ?? v))}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">{t("master_data.category.none")}</SelectItem>
                      {uom.map((u) => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name} ({u.code}){!u.active ? ` — ${t("master_data.uom.inactive")}` : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label>{t("master_data.products.stockable")}</Label>
                  <label className="flex h-8 items-center gap-2 text-sm">
                    <input type="checkbox" checked={isStockable} onChange={(e) => setIsStockable(e.target.checked)} />
                    {t("master_data.products.stockable")}
                  </label>
                </div>
                <div className="space-y-1">
                  <Label>{t("master_data.products.sales_price")}</Label>
                  <Input value={salesPrice} onChange={(e) => setSalesPrice(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label>{t("master_data.products.cost_price")}</Label>
                  <Input value={costPrice} onChange={(e) => setCostPrice(e.target.value)} />
                </div>
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => router.push("/master-data/products")}>
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={() => {
                    setError(null);
                    updateMutation.mutate();
                  }}
                  disabled={updateMutation.isPending || !sku || !name}
                >
                  {updateMutation.isPending ? t("common.loading") : t("common.save")}
                </Button>
              </div>
            </div>
          ),
        },
      ]}
    />
  );
}
