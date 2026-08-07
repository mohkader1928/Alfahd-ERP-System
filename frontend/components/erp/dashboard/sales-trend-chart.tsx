import { formatCurrency } from "@/lib/format-currency";
import type { SalesTrendPoint } from "@/features/reporting/api/types";

/**
 * Dashboard Enrichment: a lightweight hand-rolled SVG bar chart — six data
 * points don't justify a charting library dependency, and this keeps the
 * dashboard's bundle weight in line with the rest of this app's shared
 * components (also hand-rolled rather than pulled from a kitchen-sink UI
 * kit).
 */
// The bar track's pixel budget within the fixed-height wrapper below —
// deliberately in px, not the CSS `height: X%` this used to be. A percentage
// height only resolves against a flex child's height when that height comes
// from `align-items: stretch`; this wrapper uses `items-end` (bars anchor to
// a shared baseline instead of stretching to fill the row), which leaves
// each column's own height as `auto` — so every bar's `%` height resolved
// against nothing and silently rendered at 0px, regardless of the data.
const BAR_TRACK_PX = 112;

function formatCompact(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(0);
}

export function SalesTrendChart({ points }: { points: SalesTrendPoint[] }) {
  const values = points.map((p) => Number(p.total));
  const max = Math.max(...values, 1);
  const width = 100 / points.length;

  return (
    <div className="flex h-44 items-end gap-2 px-1">
      {points.map((p) => {
        const value = Number(p.total);
        const barPx = Math.max((value / max) * BAR_TRACK_PX, value > 0 ? 6 : 2);
        const [year, month] = p.period_label.split("-");
        const monthLabel = new Date(Number(year), Number(month) - 1, 1).toLocaleDateString("en-US", {
          month: "short",
        });
        return (
          <div
            key={p.period_label}
            className="flex flex-1 flex-col items-center justify-end gap-1"
            style={{ maxWidth: `${width}%` }}
            title={`${monthLabel}: ${formatCurrency(p.total)}`}
          >
            <span className="text-[10px] font-medium tabular-nums text-foreground">
              {value > 0 ? formatCompact(value) : ""}
            </span>
            <div
              className="w-full min-w-[8px] rounded-t-sm bg-primary transition-all hover:bg-primary/80"
              style={{ height: `${barPx}px` }}
            />
            <span className="text-[10px] text-muted-foreground">{monthLabel}</span>
          </div>
        );
      })}
    </div>
  );
}
