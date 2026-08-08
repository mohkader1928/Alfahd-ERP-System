/**
 * UI/UX Foundation milestone: one shared status→Badge-variant mapping.
 * Before this, ~10 screens each hardcoded their own
 * `status === "confirmed" ? "default" : "secondary"` ternary (see
 * docs/18-ui-ux-audit.md, cross-cutting finding A2/status section) — every
 * other real status value (rejected, cancelled, mismatched, ...) silently
 * fell into the same "secondary" bucket as "draft", with no visual
 * distinction. Reuses the Badge component's existing variant set
 * (components/ui/badge.tsx: default/secondary/destructive/outline/ghost/link)
 * — no new color or variant is introduced.
 */
export type BadgeVariant = "default" | "secondary" | "destructive" | "warning" | "outline";

const POSITIVE = new Set([
  "confirmed",
  "posted",
  "paid",
  "approved",
  "cleared",
  "reported",
  "active",
  "current",
]);

const NEGATIVE = new Set([
  "rejected",
  "cancelled",
  "canceled",
  "mismatched",
  "void",
  "voided",
  "overdue",
  "failed",
]);

// Neither fully resolved nor rejected — an open state that still needs a
// decision (e.g. a PO left mid-receipt). Distinct from POSITIVE/NEGATIVE
// so it doesn't silently blend into the "secondary" default like "draft".
const WARNING = new Set(["partially_received"]);

export function statusVariant(status: string | null | undefined): BadgeVariant {
  const s = (status ?? "").toLowerCase();
  if (NEGATIVE.has(s)) return "destructive";
  if (WARNING.has(s)) return "warning";
  if (POSITIVE.has(s)) return "default";
  return "secondary";
}
