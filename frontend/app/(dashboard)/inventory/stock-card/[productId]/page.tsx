"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ERPListView, type ERPColumn } from "@/components/erp/list-view/erp-list-view";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { inventoryApi } from "@/features/inventory/api/client";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { formatQty } from "@/lib/format-qty";
import { sourceDocumentHref, sourceDocumentLabelKey } from "@/lib/source-document-links";
import type { StockMove } from "@/features/inventory/api/types";

export default function StockCardPage({ params }: { params: Promise<{ productId: string }> }) {
  const { productId } = use(params);
  const { t, locale } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;

  const productQuery = useQuery({
    queryKey: ["product", companyId, productId],
    queryFn: () => identityApi.getProduct(companyId, productId),
  });
  const movesQuery = useQuery({
    queryKey: ["stock-moves", companyId, productId],
    queryFn: () => inventoryApi.listStockMoves(companyId, productId),
  });

  const columns: ERPColumn<StockMove>[] = [
    {
      key: "moved_at",
      header: t("inventory.moves.date"),
      sortable: true,
      sortValue: (r) => r.moved_at,
      render: (r) => formatDate(r.moved_at, locale),
    },
    {
      key: "move_type",
      header: t("inventory.moves.type"),
      sortable: true,
      sortValue: (r) => r.move_type,
      render: (r) => <Badge variant="secondary">{r.move_type}</Badge>,
    },
    { key: "qty", header: t("inventory.moves.qty"), align: "end", sortable: true, sortValue: (r) => Number(r.qty), render: (r) => formatQty(r.qty) },
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
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={() => router.push("/inventory")}>
        <ArrowLeft className="h-4 w-4" />
        {t("common.back")}
      </Button>
      <div className="flex items-center gap-3">
        <EntityImage src={productQuery.data?.image_path} name={productQuery.data?.name ?? ""} size="lg" shape="square" />
        <div>
          <h1 className="text-2xl font-semibold">{productQuery.data?.name ?? t("common.loading")}</h1>
          <p className="text-sm text-muted-foreground">{t("inventory.stock_card.title")}</p>
        </div>
      </div>
      <ERPListView
        title={t("inventory.stock_card.title")}
        columns={columns}
        rows={movesQuery.data}
        rowKey={(r) => r.id}
        isLoading={movesQuery.isLoading}
        isError={movesQuery.isError}
        errorMessage={movesQuery.error instanceof ApiError ? movesQuery.error.detail : undefined}
        onRetry={() => movesQuery.refetch()}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["stock-moves", companyId, productId] })}
        searchText={(r) => r.move_type}
        searchPlaceholder={t("list.search_placeholder")}
        emptyDescription={t("inventory.stock_card.empty_description")}
      />
    </div>
  );
}
