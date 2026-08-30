"use client";

import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n/config";

type Preset = "current_month" | "previous_month" | "current_quarter" | "current_year";

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function toIsoDate(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/** Commercial Performance Stage 3 (Part A): the Current Month / Previous
 * Month / Current Quarter / Current Year presets, computed client-side —
 * no backend preset param exists (or is needed); this just fills the same
 * plain date_from/date_to inputs every report already accepts. Selecting
 * a preset doesn't lock the date inputs — the user can still fine-tune
 * them afterward, which is the "Custom Date Range" case. */
export function computePresetRange(preset: Preset): { from: string; to: string } {
  const today = new Date();
  const y = today.getFullYear();
  const m = today.getMonth();
  switch (preset) {
    case "current_month":
      return { from: toIsoDate(new Date(y, m, 1)), to: toIsoDate(new Date(y, m + 1, 0)) };
    case "previous_month":
      return { from: toIsoDate(new Date(y, m - 1, 1)), to: toIsoDate(new Date(y, m, 0)) };
    case "current_quarter": {
      const quarterStartMonth = Math.floor(m / 3) * 3;
      return { from: toIsoDate(new Date(y, quarterStartMonth, 1)), to: toIsoDate(new Date(y, quarterStartMonth + 3, 0)) };
    }
    case "current_year":
      return { from: toIsoDate(new Date(y, 0, 1)), to: toIsoDate(new Date(y, 11, 31)) };
  }
}

export function DateRangePresetFilter({
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
}: {
  dateFrom: string;
  setDateFrom: (v: string) => void;
  dateTo: string;
  setDateTo: (v: string) => void;
}) {
  const { t } = useI18n();

  function applyPreset(value: string | null) {
    if (!value) return;
    const range = computePresetRange(value as Preset);
    setDateFrom(range.from);
    setDateTo(range.to);
  }

  return (
    <div className="flex flex-wrap gap-4">
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{t("filters.preset.label")}</Label>
        <Select onValueChange={applyPreset}>
          <SelectTrigger className="h-8 w-44 text-sm">
            <SelectValue placeholder={t("filters.preset.custom")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="current_month">{t("filters.preset.current_month")}</SelectItem>
            <SelectItem value="previous_month">{t("filters.preset.previous_month")}</SelectItem>
            <SelectItem value="current_quarter">{t("filters.preset.current_quarter")}</SelectItem>
            <SelectItem value="current_year">{t("filters.preset.current_year")}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{t("sales.reports.date_from")}</Label>
        <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="h-8 w-40 text-sm" />
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{t("sales.reports.date_to")}</Label>
        <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="h-8 w-40 text-sm" />
      </div>
    </div>
  );
}
