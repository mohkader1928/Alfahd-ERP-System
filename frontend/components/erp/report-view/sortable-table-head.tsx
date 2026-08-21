"use client";

import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { SortState } from "@/lib/use-sorted-rows";

/**
 * Owner request: every report/subledger-style table (Trial Balance,
 * General Ledger, Customer/Vendor Subledger, AR/AP Aging, etc.) is built
 * on `ReportView`, which -- unlike `ERPListView` -- has no `columns`
 * concept and no sort mechanism at all (each screen hand-rolls its own
 * <Table>). This is the same clickable-header + arrow-icon treatment
 * `ERPListView` already uses (erp-list-view.tsx), factored out so any
 * bespoke report table can drop it in without re-implementing the icon
 * logic — pairs with the `useSortedRows` hook for the actual sort state.
 */
export function SortableTableHead({
  sortKey,
  sort,
  onSort,
  align,
  className,
  children,
}: {
  sortKey: string;
  sort: SortState | null;
  onSort: (key: string) => void;
  align?: "start" | "end";
  className?: string;
  children: React.ReactNode;
}) {
  const active = sort?.key === sortKey;
  return (
    <TableHead className={cn(align === "end" && "text-end", className)}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="inline-flex items-center gap-1 hover:text-foreground"
      >
        {children}
        {active ? (
          sort!.dir === "asc" ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-40" />
        )}
      </button>
    </TableHead>
  );
}
