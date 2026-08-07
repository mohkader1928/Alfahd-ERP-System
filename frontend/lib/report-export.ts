/**
 * Standard Reporting Framework — one download trigger used by every report
 * tab's Export PDF/Excel buttons, so each report doesn't reimplement blob
 * fetch + auth headers + save-as.
 */
import { apiClient } from "@/lib/api-client";
import { toastError } from "@/lib/toast";

export async function downloadReportExport(
  path: string,
  params: Record<string, string | undefined>,
  format: "pdf" | "xlsx",
  companyId: string,
  branchId?: string | null
): Promise<void> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") qs.set(key, value);
  }
  qs.set("format", format);

  const { blob, filename } = await apiClient.getBlob(`${path}?${qs.toString()}`, { companyId, branchId });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** `<ReportView onExportPdf={...} onExportExcel={...}>` props for one report — every
 * report tab spreads this instead of hand-wiring the same two handlers. */
export function reportExportHandlers(
  path: string,
  params: Record<string, string | undefined>,
  companyId: string,
  branchId?: string | null
): { onExportPdf: () => void; onExportExcel: () => void } {
  const run = (format: "pdf" | "xlsx") => () =>
    downloadReportExport(path, params, format, companyId, branchId).catch((e) =>
      toastError(e instanceof Error ? e.message : String(e))
    );
  return { onExportPdf: run("pdf"), onExportExcel: run("xlsx") };
}
