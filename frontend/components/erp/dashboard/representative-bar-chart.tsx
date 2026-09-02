import { formatCurrency } from "@/lib/format-currency";

export interface RepresentativeBarPoint {
  label: string;
  value: number;
}

/** Commercial Performance Stage 3 (Part E): horizontal magnitude bars for
 * "X by Representative" — reused for Sales, Collections, and Net
 * Commission. A representative list is unbounded cardinality (unlike the
 * fixed 4-quarter donut), so per the dataviz rule this stays single-hue
 * (never a generated categorical hue per rep) — same hand-rolled CSS-bar
 * approach as `SalesTrendChart`, just laid out horizontally since labels
 * are names, not short month abbreviations. Capped to the top 8 by value
 * so the list stays readable regardless of how many reps a company has. */
const MAX_BARS = 8;

export function RepresentativeBarChart({
  points,
  colorClassName,
}: {
  points: RepresentativeBarPoint[];
  colorClassName: string;
}) {
  const top = [...points]
    .filter((p) => p.value !== 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, MAX_BARS);
  const max = Math.max(...top.map((p) => p.value), 1);

  return (
    <div className="space-y-2">
      {top.map((p) => (
        <div key={p.label} className="flex items-center gap-2 text-xs">
          <span className="w-24 shrink-0 truncate text-muted-foreground" title={p.label}>
            {p.label}
          </span>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className={`h-full rounded-full ${colorClassName}`}
              style={{ width: `${Math.max((p.value / max) * 100, 4)}%` }}
            />
          </div>
          <span className="w-20 shrink-0 text-end tabular-nums font-medium">{formatCurrency(p.value)}</span>
        </div>
      ))}
    </div>
  );
}
