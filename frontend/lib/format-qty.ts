/**
 * Shared quantity formatter — mirrors format-currency.ts's reasoning but
 * for non-monetary quantities. Backend quantities carry 4-6 decimal places
 * of internal precision (StockQuant/StockMove/StockLayer are NUMERIC(18,6),
 * kept that precise so moving-average costing never loses a fraction — see
 * InventoryValuationService's SIX_DP constant), but every report screen
 * rendered that raw string directly (e.g. "12.000000"), which is precision
 * noise for a human reading a report. Trims to at most 2 decimal places,
 * dropping trailing zeros entirely for whole quantities rather than forcing
 * ".00" the way money does — a stock report reads "12", not "12.00".
 */
export function formatQty(qty: string | number | null | undefined): string {
  const value = qty == null ? 0 : typeof qty === "string" ? Number(qty) : qty;
  return (Number.isFinite(value) ? value : 0).toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}
