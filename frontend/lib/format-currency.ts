/**
 * UI/UX Foundation milestone: the one shared money formatter. Before this,
 * only Dashboard/Accounting/Payments formatted amounts at all (each with
 * its own local helper); Sales/Purchasing/Inventory rendered the raw API
 * string (e.g. "1250.0000") — see docs/18-ui-ux-audit.md, finding A2.
 *
 * Always renders Western digits with "en-US" grouping regardless of the
 * app's active locale — this matches what was already observed live on the
 * Dashboard in both Arabic and English (Number(...).toLocaleString(undefined, ...)
 * happened to produce Western digits there), and is the norm for financial
 * figures in Saudi business software. Explicit "en-US" (not `undefined`)
 * makes that guaranteed rather than incidental.
 */
export function formatCurrency(amount: string | number | null | undefined, currencyCode = "SAR"): string {
  const value = amount == null ? 0 : typeof amount === "string" ? Number(amount) : amount;
  const formatted = (Number.isFinite(value) ? value : 0).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${formatted} ${currencyCode}`;
}
