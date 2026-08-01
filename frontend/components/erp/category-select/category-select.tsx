"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n/config";
import type { ProductCategory } from "@/features/identity/api/types";

export interface CategoryNode {
  category: ProductCategory;
  depth: number;
  path: string;
}

/** Depth-first flatten so children always render directly under their
 * parent, each carrying its full "Electrical / Lighting / LED Panels" path
 * for display and its depth for indentation. Exported for reuse anywhere
 * else a category needs its human-readable path (filters, breadcrumbs). */
export function flattenTree(categories: ProductCategory[], parentId: string | null = null, depth = 0): CategoryNode[] {
  const children = categories
    .filter((c) => c.parent_id === parentId)
    .sort((a, b) => a.name.localeCompare(b.name));
  const result: CategoryNode[] = [];
  for (const category of children) {
    result.push({ category, depth, path: category.name });
    result.push(...flattenTree(categories, category.id, depth + 1).map((n) => ({ ...n, path: `${category.name} / ${n.path}` })));
  }
  return result;
}

function descendantIds(categories: ProductCategory[], rootId: string): Set<string> {
  const ids = new Set<string>();
  let frontier = [rootId];
  while (frontier.length > 0) {
    const next: string[] = [];
    for (const parentId of frontier) {
      for (const c of categories) {
        if (c.parent_id === parentId && !ids.has(c.id)) {
          ids.add(c.id);
          next.push(c.id);
        }
      }
    }
    frontier = next;
  }
  return ids;
}

interface CategorySelectProps {
  categories: ProductCategory[];
  value: string | null;
  onChange: (id: string | null) => void;
  /** When editing a category, pass its own id so it (and its descendants,
   * which would otherwise let the UI offer a choice the backend rejects
   * as a circular hierarchy) are excluded from the option list. */
  excludeId?: string;
  placeholder?: string;
}

export function CategorySelect({ categories, value, onChange, excludeId, placeholder }: CategorySelectProps) {
  const { t } = useI18n();
  const excluded = excludeId ? new Set([excludeId, ...descendantIds(categories, excludeId)]) : new Set<string>();
  const nodes = flattenTree(categories).filter((n) => !excluded.has(n.category.id));

  return (
    <Select value={value ?? "__none__"} onValueChange={(v) => onChange(v === "__none__" ? null : (v ?? null))}>
      <SelectTrigger className="w-full">
        <SelectValue placeholder={placeholder ?? t("master_data.category.select_placeholder")}>
          {(v: string) => {
            if (v === "__none__") return t("master_data.category.none");
            return nodes.find((n) => n.category.id === v)?.path ?? v;
          }}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__none__">{t("master_data.category.none")}</SelectItem>
        {nodes.map((n) => (
          <SelectItem key={n.category.id} value={n.category.id}>
            <span style={{ paddingInlineStart: `${n.depth * 14}px` }}>
              {n.depth > 0 ? "— " : ""}
              {n.category.name}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
