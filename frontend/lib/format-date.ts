/**
 * UI/UX Professional pass, Bundle A: the one shared date formatter — before
 * this, no date formatter existed anywhere in the app (confirmed by audit);
 * every date column rendered the raw ISO string (e.g. "2026-08-04") as-is.
 * That's at least internally consistent, but not locale-aware and not the
 * "Consistent date/number formatting" the current UI/UX pass calls for.
 *
 * Mirrors `formatCurrency`'s pattern: forces Western (Latin) digits via
 * `numberingSystem: "latn"` regardless of locale, matching the existing
 * convention that numeric/financial data stays in Western digits even in
 * the Arabic UI — only the month name and field order should localize.
 */
export function formatDate(value: string | null | undefined, locale: "en" | "ar" = "en"): string {
  if (!value) return "—";
  const date = new Date(value.length <= 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale === "ar" ? "ar-SA" : "en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    numberingSystem: "latn",
  }).format(date);
}
