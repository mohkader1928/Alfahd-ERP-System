"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n/config";

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

interface PaginationBarProps {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

/**
 * Phase 17A shared pagination control, used by both ERPListView and
 * ReportView so paging looks and behaves identically everywhere. RTL-aware:
 * "previous"/"next" map to logical start/end, not literal left/right —
 * `dir` flips which icon means which, the label semantics never change.
 */
export function PaginationBar({ page, pageSize, totalItems, onPageChange, onPageSizeChange }: PaginationBarProps) {
  const { t, dir } = useI18n();
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const from = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, totalItems);

  const PrevIcon = dir === "rtl" ? ChevronRight : ChevronLeft;
  const NextIcon = dir === "rtl" ? ChevronLeft : ChevronRight;
  const FirstIcon = dir === "rtl" ? ChevronsRight : ChevronsLeft;
  const LastIcon = dir === "rtl" ? ChevronsLeft : ChevronsRight;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-sm text-muted-foreground">
      <div className="flex items-center gap-2">
        <span>{t("list.rows_per_page")}</span>
        <Select value={String(pageSize)} onValueChange={(v) => v && onPageSizeChange(Number(v))}>
          <SelectTrigger className="h-7 w-16">
            <SelectValue>{(value: string) => value}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZE_OPTIONS.map((size) => (
              <SelectItem key={size} value={String(size)}>
                {size}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-3">
        <span>
          {totalItems === 0 ? t("list.no_rows") : t("list.range_of_total").replace("{from}", String(from)).replace("{to}", String(to)).replace("{total}", String(totalItems))}
        </span>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" disabled={page <= 1} onClick={() => onPageChange(1)}>
            <FirstIcon className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
            <PrevIcon className="h-3.5 w-3.5" />
          </Button>
          <span className="px-1 tabular-nums">
            {page} / {totalPages}
          </span>
          <Button variant="ghost" size="icon-sm" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
            <NextIcon className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" disabled={page >= totalPages} onClick={() => onPageChange(totalPages)}>
            <LastIcon className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
