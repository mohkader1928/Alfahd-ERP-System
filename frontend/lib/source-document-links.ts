/**
 * Milestone 1b — Traceability: resolves a Journal Entry's `source_table`
 * (already stored on every posted entry since the earliest modules, just
 * never surfaced until now) to a real page, where one exists today.
 *
 * `sales_invoice`, `payment`, and (Bundle C) `vendor_bill` have a real
 * detail screen. Everything else (goods_receipt, goods_receipt_line,
 * cycle_count_line, ...) returns no href — callers must show the source
 * type as plain text in that case rather than a broken link. Extending
 * this map is the only change needed once a module gains its own detail
 * page.
 */
const SOURCE_DOCUMENT_HREF: Record<string, (id: string) => string> = {
  sales_invoice: (id) => `/sales/invoices/${id}`,
  payment: (id) => `/payments/${id}`,
  vendor_bill: (id) => `/purchasing/bills/${id}`,
  cycle_count: (id) => `/inventory/cycle-counts/${id}`,
  // Global Search result types (Professional Workspace Layer) — not JE
  // source documents, but the same "type -> real detail page" map.
  partner: (id) => `/master-data/partners/${id}`,
  product: (id) => `/master-data/products/${id}`,
  sales_quotation: (id) => `/sales/quotations/${id}`,
  sales_order: (id) => `/sales/orders/${id}`,
  purchase_order: (id) => `/purchasing/orders/${id}`,
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
  cycle_count: "accounting.source.cycle_count",
  manual_receipt: "accounting.source.manual_receipt",
  stock_transfer: "accounting.source.stock_transfer",
};

export function sourceDocumentLabelKey(sourceTable: string | null): string | null {
  if (!sourceTable) return null;
  return SOURCE_DOCUMENT_LABEL_KEY[sourceTable] ?? null;
}
