"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, Columns3, Download, Plus, RefreshCw, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Breadcrumbs, type BreadcrumbItem } from "@/components/erp/breadcrumbs/breadcrumbs";
import { Can } from "@/components/erp/permissions/can";
import { EmptyState } from "@/components/erp/states/empty-state";
import { ErrorState } from "@/components/erp/states/error-state";
import { PaginationBar } from "@/components/erp/list-view/pagination-bar";
import { useI18n } from "@/lib/i18n/config";

export interface ERPColumn<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  align?: "start" | "end";
  sortable?: boolean;
  sortValue?: (row: T) => string | number;
  defaultVisible?: boolean;
}

interface ActionConfig {
  label: string;
  href?: string;
  onClick?: () => void;
  permission?: string | string[];
}

export interface ERPListViewProps<T> {
  title: string;
  breadcrumbs?: BreadcrumbItem[];
  columns: ERPColumn<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  /** Shared drill-down convention (per the UI/UX Professional pass): when
   * a row represents a document/record with a real detail page, pass its
   * href here to get double-click-to-open + Enter-to-open (when the row
   * is keyboard-focused) for free, plus a trailing chevron as the
   * discoverability cue — on top of, not instead of, the primary column's
   * own Link (double-click is never the *only* way in). */
  getRowHref?: (row: T) => string | undefined;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  onRefresh?: () => void;
  searchPlaceholder?: string;
  searchText?: (row: T) => string;
  filters?: React.ReactNode;
  createAction?: ActionConfig;
  exportAction?: ActionConfig;
  rowActions?: (row: T) => React.ReactNode;
  selectable?: boolean;
  bulkActions?: (selected: T[], clearSelection: () => void) => React.ReactNode;
  emptyTitle?: string;
  emptyDescription?: string;
  pageSizeDefault?: number;
}

/**
 * Phase 17A shared ERP list view (Part 2). Every future module list should
 * be built on this instead of a bespoke <Table> — search, sort, pagination,
 * column visibility, row selection, and all UI states are handled here once.
 * Sorting/paging/search run client-side over `rows` because no backend list
 * endpoint currently supports server-side paging (Phase 17 blueprint §3) —
 * data volumes at this stage (≤500-row `limit`s) make that the right
 * tradeoff; a `Page<T>`-based server-side variant can be added later without
 * changing this component's external contract.
 */
export function ERPListView<T>({
  title,
  breadcrumbs,
  columns,
  rows,
  rowKey,
  getRowHref,
  isLoading,
  isError,
  errorMessage,
  onRetry,
  onRefresh,
  searchPlaceholder,
  searchText,
  filters,
  createAction,
  exportAction,
  rowActions,
  selectable,
  bulkActions,
  emptyTitle,
  emptyDescription,
  pageSizeDefault = 25,
}: ERPListViewProps<T>) {
  const { t } = useI18n();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(pageSizeDefault);
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const visibleColumns = columns.filter((c) => !hiddenColumns.has(c.key));

  const filteredRows = useMemo(() => {
    if (!rows) return [];
    if (!search.trim() || !searchText) return rows;
    const needle = search.trim().toLowerCase();
    return rows.filter((row) => searchText(row).toLowerCase().includes(needle));
  }, [rows, search, searchText]);

  const sortedRows = useMemo(() => {
    if (!sort) return filteredRows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortValue) return filteredRows;
    const copy = [...filteredRows];
    copy.sort((a, b) => {
      const av = column.sortValue!(a);
      const bv = column.sortValue!(b);
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [filteredRows, sort, columns]);

  const totalItems = sortedRows.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const clampedPage = Math.min(page, totalPages);
  const pagedRows = sortedRows.slice((clampedPage - 1) * pageSize, clampedPage * pageSize);

  function toggleSort(key: string) {
    setSort((prev) => {
      if (prev?.key !== key) return { key, dir: "asc" };
      if (prev.dir === "asc") return { key, dir: "desc" };
      return null;
    });
  }

  function toggleSelected(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const selectedRows = rows?.filter((r) => selected.has(rowKey(r))) ?? [];
  const allPagedSelected = pagedRows.length > 0 && pagedRows.every((r) => selected.has(rowKey(r)));

  return (
    <div className="space-y-3">
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <div className="flex items-center gap-2">
          {onRefresh && (
            <Button variant="ghost" size="icon-sm" onClick={onRefresh} title={t("common.refresh")}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          )}
          {exportAction && (
            <Can permission={exportAction.permission ?? "reporting.export"}>
              <Button variant="outline" size="sm" onClick={exportAction.onClick}>
                <Download className="h-4 w-4" />
                {exportAction.label ?? t("common.export")}
              </Button>
            </Can>
          )}
          {createAction &&
            (createAction.permission ? (
              <Can permission={createAction.permission}>
                <Button size="sm" onClick={createAction.onClick} render={createAction.href ? <Link href={createAction.href} /> : undefined}>
                  <Plus className="h-4 w-4" />
                  {createAction.label}
                </Button>
              </Can>
            ) : (
              <Button size="sm" onClick={createAction.onClick} render={createAction.href ? <Link href={createAction.href} /> : undefined}>
                <Plus className="h-4 w-4" />
                {createAction.label}
              </Button>
            ))}
        </div>
      </div>

      <Card>
        <CardHeader className="gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {searchText && (
              <div className="relative w-64">
                <Search className="pointer-events-none absolute start-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(1);
                  }}
                  placeholder={searchPlaceholder ?? t("list.search_placeholder")}
                  className="ps-7"
                />
                {search && (
                  <button
                    type="button"
                    onClick={() => setSearch("")}
                    className="absolute end-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            )}
            {filters}
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="outline" size="sm" />}>
                <Columns3 className="h-4 w-4" />
                {t("list.columns")}
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {columns.map((col) => (
                  <DropdownMenuCheckboxItem
                    key={col.key}
                    checked={!hiddenColumns.has(col.key)}
                    onCheckedChange={(checked) =>
                      setHiddenColumns((prev) => {
                        const next = new Set(prev);
                        if (checked) next.delete(col.key);
                        else next.add(col.key);
                        return next;
                      })
                    }
                  >
                    {col.header}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          {selectable && selected.size > 0 && bulkActions && (
            <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm">
              <span className="font-medium">{t("list.selected_count").replace("{count}", String(selected.size))}</span>
              {bulkActions(selectedRows, () => setSelected(new Set()))}
              <Button variant="ghost" size="xs" onClick={() => setSelected(new Set())}>
                {t("list.clear_selection")}
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          <Table>
            <TableHeader>
              <TableRow>
                {selectable && (
                  <TableHead className="w-8">
                    <input
                      type="checkbox"
                      checked={allPagedSelected}
                      onChange={(e) =>
                        setSelected((prev) => {
                          const next = new Set(prev);
                          for (const r of pagedRows) {
                            if (e.target.checked) next.add(rowKey(r));
                            else next.delete(rowKey(r));
                          }
                          return next;
                        })
                      }
                    />
                  </TableHead>
                )}
                {visibleColumns.map((col) => (
                  <TableHead key={col.key} className={col.align === "end" ? "text-end" : undefined}>
                    {col.sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(col.key)}
                        className="inline-flex items-center gap-1 hover:text-foreground"
                      >
                        {col.header}
                        {sort?.key === col.key ? (
                          sort.dir === "asc" ? (
                            <ArrowUp className="h-3 w-3" />
                          ) : (
                            <ArrowDown className="h-3 w-3" />
                          )
                        ) : (
                          <ArrowUpDown className="h-3 w-3 opacity-40" />
                        )}
                      </button>
                    ) : (
                      col.header
                    )}
                  </TableHead>
                ))}
                {rowActions && <TableHead className="w-8" />}
                {getRowHref && <TableHead className="w-6" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={visibleColumns.length + (selectable ? 1 : 0) + (rowActions ? 1 : 0) + (getRowHref ? 1 : 0)}>
                      <Skeleton className="h-6 w-full" />
                    </TableCell>
                  </TableRow>
                ))}

              {!isLoading && isError && (
                <TableRow>
                  <TableCell colSpan={visibleColumns.length + (selectable ? 1 : 0) + (rowActions ? 1 : 0) + (getRowHref ? 1 : 0)}>
                    <ErrorState message={errorMessage} onRetry={onRetry} />
                  </TableCell>
                </TableRow>
              )}

              {!isLoading && !isError && pagedRows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={visibleColumns.length + (selectable ? 1 : 0) + (rowActions ? 1 : 0) + (getRowHref ? 1 : 0)}>
                    <EmptyState title={emptyTitle ?? t("list.empty_title")} description={emptyDescription} />
                  </TableCell>
                </TableRow>
              )}

              {!isLoading &&
                !isError &&
                pagedRows.map((row) => {
                  const key = rowKey(row);
                  const href = getRowHref?.(row);
                  return (
                    <TableRow
                      key={key}
                      className={href ? "cursor-pointer" : undefined}
                      tabIndex={href ? 0 : undefined}
                      onDoubleClick={href ? () => router.push(href) : undefined}
                      onKeyDown={
                        href
                          ? (e) => {
                              if (e.key === "Enter") router.push(href);
                            }
                          : undefined
                      }
                    >
                      {selectable && (
                        <TableCell>
                          <input type="checkbox" checked={selected.has(key)} onChange={() => toggleSelected(key)} />
                        </TableCell>
                      )}
                      {visibleColumns.map((col) => (
                        <TableCell key={col.key} className={col.align === "end" ? "text-end" : undefined}>
                          {col.render(row)}
                        </TableCell>
                      ))}
                      {rowActions && <TableCell className="text-end">{rowActions(row)}</TableCell>}
                      {getRowHref && (
                        <TableCell className="text-end">
                          {href && <ChevronRight className="h-4 w-4 text-muted-foreground rtl:rotate-180" />}
                        </TableCell>
                      )}
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>

          {!isLoading && !isError && totalItems > 0 && (
            <PaginationBar
              page={clampedPage}
              pageSize={pageSize}
              totalItems={totalItems}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
