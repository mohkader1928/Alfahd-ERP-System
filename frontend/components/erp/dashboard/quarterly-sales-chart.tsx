"use client";

import { useState } from "react";
import { formatCurrency } from "@/lib/format-currency";
import { useI18n } from "@/lib/i18n/config";
import type { SalesTrendPoint } from "@/features/reporting/api/types";

/**
 * Hardening Sub-stage 1 (Owner: "بها مبيعات كل ربع بالوان جذابة" — quarterly
 * sales, attractive colors): a donut chart showing each fiscal quarter's
 * share of the year's sales, built from the same monthly `sales_trend`
 * points the bar chart above it already receives — grouped into 3-month
 * quarters client-side, no new API needed.
 *
 * Colors: dataviz skill categorical slots 1-4 (blue/orange/aqua/yellow),
 * validated colorblind-safe via scripts/validate_palette.js (adjacent
 * pairlist, light + dark). Slots 3/4 sit under 3:1 contrast on the light
 * surface, so per the skill's "relief rule" every segment also carries a
 * visible direct label in the legend — never color-alone identity.
 */
const QUARTER_COLORS = [
  { bg: "bg-[#2a78d6] dark:bg-[#3987e5]", text: "text-[#2a78d6] dark:text-[#3987e5]" },
  { bg: "bg-[#eb6834] dark:bg-[#d95926]", text: "text-[#eb6834] dark:text-[#d95926]" },
  { bg: "bg-[#1baf7a] dark:bg-[#199e70]", text: "text-[#1baf7a] dark:text-[#199e70]" },
  { bg: "bg-[#eda100] dark:bg-[#c98500]", text: "text-[#eda100] dark:text-[#c98500]" },
];

const GAP = 1.2; // percent of circumference reserved as a surface-color gap between segments

function groupIntoQuarters(points: SalesTrendPoint[]) {
  const quarters: { label: string; total: number }[] = [];
  for (let i = 0; i < points.length; i += 3) {
    const chunk = points.slice(i, i + 3);
    if (chunk.length === 0) continue;
    quarters.push({
      label: `Q${quarters.length + 1}`,
      total: chunk.reduce((sum, p) => sum + Number(p.total), 0),
    });
  }
  return quarters;
}

export function QuarterlySalesChart({ points }: { points: SalesTrendPoint[] }) {
  const { t } = useI18n();
  const [hovered, setHovered] = useState<number | null>(null);
  const quarters = groupIntoQuarters(points);
  const total = quarters.reduce((sum, q) => sum + q.total, 0);

  if (total <= 0) {
    return <p className="py-12 text-center text-sm text-muted-foreground">{t("common.empty")}</p>;
  }

  // Purely functional (no accumulator mutation): each segment's cumulative
  // offset is the sum of every prior quarter's share — at most 4 quarters,
  // so the O(n^2) re-sum per segment is irrelevant.
  const segments = quarters.map((q, i) => {
    const cumulative = quarters.slice(0, i).reduce((sum, prior) => sum + (prior.total / total) * 100, 0);
    const percent = (q.total / total) * 100;
    const dash = Math.max(percent - GAP, 0);
    const offset = 25 - cumulative;
    return { ...q, percent, dash, offset, color: QUARTER_COLORS[i % QUARTER_COLORS.length] };
  });

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:justify-center">
      <div className="relative h-40 w-40 shrink-0">
        <svg viewBox="0 0 42 42" className="h-full w-full -rotate-90">
          <circle
            cx="21"
            cy="21"
            r="15.9"
            fill="none"
            className="stroke-muted"
            strokeWidth="6"
          />
          {segments.map((seg, i) => (
            <circle
              key={seg.label}
              cx="21"
              cy="21"
              r="15.9"
              fill="none"
              strokeWidth={hovered === i ? "7.5" : "6"}
              pathLength={100}
              strokeDasharray={`${seg.dash} ${100 - seg.dash}`}
              strokeDashoffset={seg.offset}
              className={`${seg.color.text} transition-all duration-150`}
              style={{ stroke: "currentColor" }}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
            />
          ))}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-[10px] text-muted-foreground">{t("dashboard.quarterly_sales.total")}</span>
          <span className="text-sm font-semibold tabular-nums">{formatCurrency(total)}</span>
        </div>
      </div>

      <div className="grid w-full grid-cols-1 gap-1.5 sm:w-auto">
        {segments.map((seg, i) => (
          <div
            key={seg.label}
            className={`flex items-center gap-2 rounded-md px-2 py-1 transition-colors ${
              hovered === i ? "bg-muted" : ""
            }`}
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered(null)}
          >
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${seg.color.bg}`} />
            <span className="w-6 shrink-0 text-xs font-medium text-foreground">{seg.label}</span>
            <span className="flex-1 text-xs tabular-nums text-muted-foreground">{formatCurrency(seg.total)}</span>
            <span className="w-10 shrink-0 text-end text-xs tabular-nums text-muted-foreground">
              {seg.percent.toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
