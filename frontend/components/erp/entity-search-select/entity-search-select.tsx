"use client";

import { useMemo } from "react";
import { Combobox, ComboboxContent, ComboboxInput, ComboboxInputGroup, ComboboxItem } from "@/components/ui/combobox";
import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { useI18n } from "@/lib/i18n/config";

export interface EntitySearchSelectItem {
  id: string;
  /** Primary display text (e.g. product/asset/partner name). */
  label: string;
  /** Secondary text shown before the label, monospace (SKU/asset code/etc). */
  code?: string;
  /** Extra text to match against while typing but not shown (e.g. name_ar,
   * vat_number) — defaults to `${code} ${label}` when omitted. */
  searchText?: string;
  imageSrc?: string | null;
  imageShape?: "circle" | "square";
}

interface EntitySearchSelectProps {
  items: EntitySearchSelectItem[];
  value: string | null;
  onChange: (id: string | null) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

/** Standard system-wide "search to pick one" input — for choosing a stock
 * item on a sales/purchase line, a fixed asset to view, a partner, etc.
 * Owner directive: any input field on this level of the system that picks
 * one entity out of a list should let the user type to filter instead of
 * scrolling a plain dropdown, so entry stays fast as the list grows.
 * Thin app-specific wrapper over the generic `Combobox` primitives (mirrors
 * how `CategorySelect` wraps the plain `Select` for its own recurring
 * need) — callers just map their domain objects into `EntitySearchSelectItem[]`. */
export function EntitySearchSelect({ items, value, onChange, placeholder, disabled, className }: EntitySearchSelectProps) {
  const { t } = useI18n();
  const selected = useMemo(() => items.find((i) => i.id === value) ?? null, [items, value]);

  return (
    <Combobox
      items={items}
      value={selected}
      onValueChange={(item) => onChange(item?.id ?? null)}
      itemToStringLabel={(item: EntitySearchSelectItem | null) => item?.label ?? ""}
      isItemEqualToValue={(a: EntitySearchSelectItem | null, b: EntitySearchSelectItem | null) => a?.id === b?.id}
      filter={(item: EntitySearchSelectItem, query: string) => {
        const haystack = (item.searchText ?? `${item.code ?? ""} ${item.label}`).toLowerCase();
        return haystack.includes(query.trim().toLowerCase());
      }}
      disabled={disabled}
    >
      <ComboboxInputGroup className={className}>
        <ComboboxInput placeholder={placeholder ?? t("common.search_select_placeholder")} />
      </ComboboxInputGroup>
      <ComboboxContent>
        {(item: EntitySearchSelectItem) => (
          <ComboboxItem key={item.id} value={item}>
            {item.imageSrc !== undefined && (
              <EntityImage src={item.imageSrc} name={item.label} size="xs" shape={item.imageShape ?? "circle"} />
            )}
            {item.code && <span className="font-mono text-xs text-muted-foreground">{item.code}</span>}
            <span className="flex-1 truncate">{item.label}</span>
          </ComboboxItem>
        )}
      </ComboboxContent>
    </Combobox>
  );
}
