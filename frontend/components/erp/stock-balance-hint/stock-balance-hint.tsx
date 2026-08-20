"use client";

import { useQuery } from "@tanstack/react-query";
import { inventoryApi } from "@/features/inventory/api/client";
import { useI18n } from "@/lib/i18n/config";

export interface StockBalanceHintProps {
  companyId: string;
  productId: string | null | undefined;
  warehouseId: string | null | undefined;
}

// Owner request: whenever a Quotation/Sales Order/Purchase Order/Transfer
// line names a product AND a warehouse, show that product's current
// on-hand balance in that specific warehouse right next to the line — so
// the user sees what they already have before committing to buy, sell, or
// move more of it. Deliberately its own component (not inlined in a
// `.map()` over lines) because each line needs its own `useQuery` call,
// and calling hooks inside a loop body breaks React's hook-count
// invariant — a real child component keeps each line's hook calls stable
// regardless of how many lines exist.
export function StockBalanceHint({ companyId, productId, warehouseId }: StockBalanceHintProps) {
  const { t } = useI18n();
  const balanceQuery = useQuery({
    queryKey: ["stock-balance", companyId, productId, warehouseId],
    queryFn: () => inventoryApi.getStockBalance(companyId, productId!, warehouseId!),
    enabled: !!productId && !!warehouseId,
  });

  if (!productId || !warehouseId || !balanceQuery.data) return null;

  // Owner request: a balance at or below zero (out of stock, or oversold
  // negative via FR-INV-007) must stand out in red rather than blend in
  // with the same muted color as a healthy balance.
  const isNonPositive = Number(balanceQuery.data.qty_on_hand) <= 0;

  return (
    <p className={isNonPositive ? "text-xs font-medium text-destructive" : "text-xs text-muted-foreground"}>
      {t("inventory.stock_balance.current")}: <span className="tabular-nums">{balanceQuery.data.qty_on_hand}</span>
    </p>
  );
}
