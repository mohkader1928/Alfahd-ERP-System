"use client";

import { Download, Printer, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Breadcrumbs, type BreadcrumbItem } from "@/components/erp/breadcrumbs/breadcrumbs";
import { EmptyState } from "@/components/erp/states/empty-state";
import { ErrorState } from "@/components/erp/states/error-state";
import { useI18n } from "@/lib/i18n/config";

interface KpiSummaryItem {
  label: string;
  value: string;
}

interface ReportViewProps {
  title: string;
  description?: string;
  breadcrumbs?: BreadcrumbItem[];
  filterArea?: React.ReactNode;
  onApply?: () => void;
  onReset?: () => void;
  onExport?: () => void;
  onPrint?: () => void;
  kpis?: KpiSummaryItem[];
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  isEmpty?: boolean;
  emptyTitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

/**
 * Phase 17A shared ERP report shell (Part 5). Every future report (General
 * Ledger, aging, P&L, sales/purchase analysis...) should render its own
 * table/grouping/totals as `children` inside this header/body/footer
 * structure rather than each report reinventing the filter row and export
 * buttons. `print:` utility classes hide the filter/action chrome so the
 * printed page (Part 5 "print-friendly layout") shows only the report body.
 */
export function ReportView({
  title,
  description,
  breadcrumbs,
  filterArea,
  onApply,
  onReset,
  onExport,
  onPrint,
  kpis,
  isLoading,
  isError,
  errorMessage,
  onRetry,
  isEmpty,
  emptyTitle,
  children,
  footer,
}: ReportViewProps) {
  const { t } = useI18n();

  return (
    <div className="space-y-4">
      <div className="print:hidden">{breadcrumbs && <Breadcrumbs items={breadcrumbs} />}</div>

      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>

      {filterArea && (
        <Card className="print:hidden">
          <CardContent className="flex flex-wrap items-end justify-between gap-3 pt-4">
            <div className="flex flex-wrap items-end gap-2">{filterArea}</div>
            <div className="flex items-center gap-2">
              {onApply && (
                <Button size="sm" onClick={onApply}>
                  {t("filters.apply")}
                </Button>
              )}
              {onReset && (
                <Button size="sm" variant="ghost" onClick={onReset}>
                  <RotateCcw className="h-4 w-4" />
                  {t("filters.reset")}
                </Button>
              )}
              {onExport && (
                <Button size="sm" variant="outline" onClick={onExport}>
                  <Download className="h-4 w-4" />
                  {t("common.export")}
                </Button>
              )}
              {onPrint && (
                <Button size="sm" variant="outline" onClick={onPrint}>
                  <Printer className="h-4 w-4" />
                  {t("common.print")}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {kpis && kpis.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {kpis.map((kpi) => (
            <Card key={kpi.label}>
              <CardContent className="pt-4">
                <p className="text-xs text-muted-foreground">{kpi.label}</p>
                <p className="text-lg font-semibold tabular-nums">{kpi.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader className="sr-only">
          <span>{title}</span>
        </CardHeader>
        <CardContent className="space-y-3 pt-4">
          {isLoading && <Skeleton className="h-64 w-full" />}
          {!isLoading && isError && <ErrorState message={errorMessage} onRetry={onRetry} />}
          {!isLoading && !isError && isEmpty && <EmptyState title={emptyTitle ?? t("list.empty_title")} />}
          {!isLoading && !isError && !isEmpty && children}
        </CardContent>
      </Card>

      {footer && <div className="print:hidden">{footer}</div>}
    </div>
  );
}
