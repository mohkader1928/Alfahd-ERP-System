/**
 * Milestone 1b — Traceability: resolves a Journal Entry's `source_table`
 * (already stored on every posted entry since the earliest modules, just
 * never surfaced until now) to a real page, where one exists today.
 *
 * Only `sales_invoice` and `payment` have a real detail screen right now.
 * Everything else (vendor_bill, goods_receipt, goods_receipt_line,
 * cycle_count_line, ...) returns no href — callers must show the source
 * type as plain text in that case rather than a broken link. Extending
 * this map is the only change needed once a module gains its own detail
 * page (e.g. a future Vendor Bill screen).
 */
const SOURCE_DOCUMENT_HREF: Record<string, (id: string) => string> = {
  sales_invoice: (id) => `/sales/invoices/${id}`,
  payment: (id) => `/payments/${id}`,
};

export function sourceDocumentHref(sourceTable: string | null, sourceId: string | null): string | null {
  if (!sourceTable || !sourceId) return null;
  const build = SOURCE_DOCUMENT_HREF[sourceTable];
  return build ? build(sourceId) : null;
}

const SOURCE_DOCUMENT_LABEL_KEY: Record<string, string> = {
  sales_invoice: "accounting.source.sales_invoice",
  payment: "accounting.source.payment",
  vendor_bill: "accounting.source.vendor_bill",
  goods_receipt: "accounting.source.goods_receipt",
  goods_receipt_line: "accounting.source.goods_receipt",
  cycle_count_line: "accounting.source.cycle_count",
};

export function sourceDocumentLabelKey(sourceTable: string | null): string | null {
  if (!sourceTable) return null;
  return SOURCE_DOCUMENT_LABEL_KEY[sourceTable] ?? null;
}
