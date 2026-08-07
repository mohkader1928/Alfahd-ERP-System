import { formatCurrency } from "@/lib/format-currency";
import type { SalesTrendPoint } from "@/features/reporting/api/types";

/**
 * Dashboard Enrichment: a lightweight hand-rolled SVG bar chart — six data
 * points don't justify a charting library dependency, and this keeps the
 * dashboard's bundle weight in line with the rest of this app's shared
 * components (also hand-rolled rather than pulled from a kitchen-sink UI
 * kit).
 */
export function SalesTrendChart({ points }: { points: SalesTrendPoint[] }) {
  const values = points.map((p) => Number(p.total));
  const max = Math.max(...values, 1);
  const width = 100 / points.length;

  return (
    <div className="flex h-40 items-end gap-2 px-1">
      {points.map((p) => {
        const value = Number(p.total);
        const heightPct = (value / max) * 100;
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
            <div
              className="w-full rounded-t-sm bg-primary/80 transition-all hover:bg-primary"
              style={{ height: `${Math.max(heightPct, value > 0 ? 4 : 1)}%` }}
            />
            <span className="text-[10px] text-muted-foreground">{monthLabel}</span>
          </div>
        );
      })}
    </div>
  );
}
