"use client";

import { EntityImage } from "@/components/erp/entity-image/entity-image";
import { useCompanyName } from "@/hooks/use-company-name";

interface ReportPrintHeaderProps {
  reportTitle: string;
  /** e.g. a partner name for a statement, or a date range for other reports. */
  subtitle?: string;
  dateRangeLabel?: string;
}

/**
 * UI/UX Professional pass, Bundle A. The Customer/Vendor Subledger tabs
 * (Milestone 1b) already had the correct print-only header — company logo
 * + legal name, hidden on screen via `print:block`/`hidden` — but every
 * other report (Trial Balance, General Ledger, Income Statement, Balance
 * Sheet, Aging) printed with no header at all. Extracted here once so
 * every report gets the same identity, instead of only the two Subledger
 * tabs having it.
 *
 * Owner-reported confusion: the applied date range was only ever shown
 * on the print-only block above (invisible on screen), so comparing two
 * report screens against each other with no visible reminder of which
 * date range each was actually run for produced numbers that looked
 * like a bug but were really just two different periods. Every report
 * in the app already passes `dateRangeLabel` into this one shared
 * component, so restating it on screen here (not print-only) fixes it
 * everywhere at once instead of touching each report tab individually.
 */
export function ReportPrintHeader({ reportTitle, subtitle, dateRangeLabel }: ReportPrintHeaderProps) {
  const { name, company } = useCompanyName();

  return (
    <>
      <div className="hidden print:block">
        <div className="flex items-center gap-2">
          <EntityImage src={company?.logo_path} name={name ?? ""} shape="square" size="sm" />
          <p className="text-base font-semibold">{name}</p>
        </div>
        <h2 className="text-lg font-semibold">
          {reportTitle}
          {subtitle ? ` — ${subtitle}` : ""}
        </h2>
        {dateRangeLabel && <p className="text-sm text-muted-foreground">{dateRangeLabel}</p>}
      </div>
      {dateRangeLabel && (
        <p className="mb-3 text-sm text-muted-foreground print:hidden">
          {subtitle ? `${subtitle} — ` : ""}
          {dateRangeLabel}
        </p>
      )}
    </>
  );
}
