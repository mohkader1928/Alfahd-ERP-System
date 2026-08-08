"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormView } from "@/components/erp/form-view/form-view";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CategorySelect } from "@/components/erp/category-select/category-select";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";

export default function NewProductPage() {
  const { t } = useI18n();
  const router = useRouter();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId);
  const queryClient = useQueryClient();

  const categoriesQuery = useQuery({
    queryKey: ["product-categories", companyId],
    queryFn: () => identityApi.listProductCategories(companyId),
  });
  const uomQuery = useQuery({
    queryKey: ["uom", companyId, "active"],
    queryFn: () => identityApi.listUom(companyId, { active: true }),
  });

  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [nameAr, setNameAr] = useState("");
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [uomId, setUomId] = useState<string | null>(null);
  const [isStockable, setIsStockable] = useState(true);
  const [salesPrice, setSalesPrice] = useState("0.00");
  const [costPrice, setCostPrice] = useState("0.00");
  const [priceHigh, setPriceHigh] = useState("");
  const [priceLow, setPriceLow] = useState("");
  const [reorderPoint, setReorderPoint] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      identityApi.createProduct(companyId, branchId, {
        sku,
        name,
        name_ar: nameAr || null,
        category_id: categoryId,
        uom_id: uomId,
        is_stockable: isStockable,
        sales_price: salesPrice,
        cost_price: costPrice,
        price_high: priceHigh || null,
        price_low: priceLow || null,
        reorder_point: reorderPoint || null,
      }),
    onSuccess: (product) => {
      queryClient.invalidateQueries({ queryKey: ["products", companyId] });
      router.push(`/master-data/products/${product.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  return (
    <FormView
      title={t("master_data.products.new")}
      breadcrumbs={[
        { label: t("nav.master_data") },
        { label: t("master_data.products.title"), href: "/master-data/products" },
        { label: t("master_data.products.new") },
      ]}
      onSave={() => {
        setError(null);
        createMutation.mutate();
      }}
      onCancel={() => router.push("/master-data/products")}
      isSaving={createMutation.isPending}
      saveDisabled={!sku || !name}
      error={error}
    >
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
          <CategorySelect categories={categoriesQuery.data ?? []} value={categoryId} onChange={setCategoryId} />
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.products.uom")}</Label>
          <Select value={uomId ?? "__none__"} onValueChange={(v) => setUomId(v === "__none__" ? null : (v ?? null))}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t("master_data.products.uom")}>
                {(v: string) => (v === "__none__" ? t("master_data.category.none") : (uomQuery.data?.find((u) => u.id === v)?.name ?? v))}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">{t("master_data.category.none")}</SelectItem>
              {uomQuery.data?.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.name} ({u.code})
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
        <div className="space-y-1">
          <Label>{t("master_data.products.price_high")}</Label>
          <Input value={priceHigh} onChange={(e) => setPriceHigh(e.target.value)} placeholder={t("master_data.products.price_optional_placeholder")} />
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.products.price_low")}</Label>
          <Input value={priceLow} onChange={(e) => setPriceLow(e.target.value)} placeholder={t("master_data.products.price_optional_placeholder")} />
        </div>
        <div className="space-y-1">
          <Label>{t("master_data.products.reorder_point")}</Label>
          <Input
            value={reorderPoint}
            onChange={(e) => setReorderPoint(e.target.value)}
            placeholder={t("master_data.products.reorder_point_placeholder")}
          />
        </div>
      </div>
    </FormView>
  );
}
