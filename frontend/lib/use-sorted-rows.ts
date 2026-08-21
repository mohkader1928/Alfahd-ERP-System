"use client";

import { useMemo, useState } from "react";

export interface SortState {
  key: string;
  dir: "asc" | "desc";
}

/**
 * Owner request: sorting on every field across every query screen,
 * including the ReportView-based ones (Trial Balance, General Ledger,
 * Customer/Vendor Subledger, AR/AP Aging, etc.) that have no shared list
 * component to opt into like ERPListView does. Same three-state
 * (asc -> desc -> none) toggle and comparator ERPListView already uses
 * internally, factored into a hook so any bespoke report table can sort
 * its own already-fetched rows without re-implementing it. Pair with
 * `SortableTableHead` for the header UI.
 */
export function useSortedRows<T>(rows: T[] | undefined, sortValues: Record<string, (row: T) => string | number>) {
  const [sort, setSort] = useState<SortState | null>(null);

  function toggleSort(key: string) {
    setSort((prev) => {
      if (prev?.key !== key) return { key, dir: "asc" };
      if (prev.dir === "asc") return { key, dir: "desc" };
      return null;
    });
  }

  const sortedRows = useMemo(() => {
    if (!rows || !sort) return rows;
    const getValue = sortValues[sort.key];
    if (!getValue) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = getValue(a);
      const bv = getValue(b);
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sort, sortValues]);

  return { sort, toggleSort, sortedRows };
}
