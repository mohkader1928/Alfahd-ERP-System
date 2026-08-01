"use client";

import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n/config";

export type FilterFieldType = "text" | "select" | "date";

export interface FilterFieldConfig {
  key: string;
  label: string;
  type: FilterFieldType;
  options?: { value: string; label: string }[];
  width?: string;
}

interface FilterBarProps {
  fields: FilterFieldConfig[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onApply?: () => void;
  onClear: () => void;
}

/**
 * Phase 17A shared filter architecture (Part 3/4). `fields` is configured
 * per screen — not every list needs every filter — and the same shape
 * (customer/vendor/product/category/warehouse/location/account/date range/
 * branch/document type/status) is what future report filters (Part 4) will
 * also be built from, so a screen's filter config and its eventual report's
 * filter config stay structurally identical.
 */
export function FilterBar({ fields, values, onChange, onApply, onClear }: FilterBarProps) {
  const { t } = useI18n();
  const activeEntries = Object.entries(values).filter(([, v]) => v);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        {fields.map((field) => (
          <div key={field.key} className="space-y-1">
            <label className="text-xs text-muted-foreground">{field.label}</label>
            {field.type === "select" ? (
              <Select value={values[field.key] ?? ""} onValueChange={(v) => onChange(field.key, v ?? "")}>
                <SelectTrigger className={field.width ?? "w-40"}>
                  <SelectValue placeholder={field.label}>
                    {(value: string) => field.options?.find((o) => o.value === value)?.label ?? value}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {field.options?.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                type={field.type === "date" ? "date" : "text"}
                value={values[field.key] ?? ""}
                onChange={(e) => onChange(field.key, e.target.value)}
                className={field.width ?? "w-40"}
              />
            )}
          </div>
        ))}
        {onApply && (
          <Button size="sm" onClick={onApply}>
            {t("filters.apply")}
          </Button>
        )}
        {activeEntries.length > 0 && (
          <Button variant="ghost" size="sm" onClick={onClear}>
            {t("filters.reset")}
          </Button>
        )}
      </div>
      {activeEntries.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {activeEntries.map(([key, value]) => {
            const field = fields.find((f) => f.key === key);
            const label = field?.options?.find((o) => o.value === value)?.label ?? value;
            return (
              <Badge key={key} variant="secondary" className="gap-1">
                {field?.label}: {label}
                <button type="button" onClick={() => onChange(key, "")} className="ms-0.5">
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            );
          })}
        </div>
      )}
    </div>
  );
}
