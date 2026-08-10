import { apiClient } from "@/lib/api-client";
import type { Page } from "@/lib/pagination";
import type { InvoiceIssueResponse, Quotation, QuotationLineIn, SalesInvoice, SalesOrder } from "./types";

export interface SalesInvoiceListFilters {
  partnerId?: string;
  status?: string;
  dateFrom?: string;
  dateTo?: string;
  invoiceType?: string;
  page?: number;
  pageSize?: number;
}

const BASE = "/api/v1/sales";

export const salesApi = {
  listQuotations: (companyId: string) => apiClient.get<Quotation[]>(`${BASE}/quotations`, { companyId }),

  createQuotation: (
    companyId: string,
    branchId: string,
    payload: { partner_id: string; quote_date: string; lines: QuotationLineIn[] }
  ) => apiClient.post<Quotation>(`${BASE}/quotations`, payload, { companyId, branchId }),

  getQuotation: (companyId: string, id: string) =>
    apiClient.get<Quotation>(`${BASE}/quotations/${id}`, { companyId }),

  confirmQuotation: (companyId: string, branchId: string, id: string) =>
    apiClient.post<SalesOrder>(`${BASE}/quotations/${id}:confirm`, undefined, { companyId, branchId }),

  listOrders: (companyId: string) => apiClient.get<SalesOrder[]>(`${BASE}/orders`, { companyId }),

  getSalesOrder: (companyId: string, id: string) => apiClient.get<SalesOrder>(`${BASE}/orders/${id}`, { companyId }),

  issueInvoice: (companyId: string, branchId: string, orderId: string) =>
    apiClient.post<InvoiceIssueResponse>(`${BASE}/orders/${orderId}:invoice`, undefined, { companyId, branchId }),

  getInvoice: (companyId: string, id: string) =>
    apiClient.get<InvoiceIssueResponse>(`${BASE}/invoices/${id}`, { companyId }),

  listInvoices: (companyId: string, filters: SalesInvoiceListFilters = {}) => {
    const qs = new URLSearchParams();
    if (filters.partnerId) qs.set("partner_id", filters.partnerId);
    if (filters.status) qs.set("status", filters.status);
    if (filters.dateFrom) qs.set("date_from", filters.dateFrom);
    if (filters.dateTo) qs.set("date_to", filters.dateTo);
    if (filters.invoiceType) qs.set("invoice_type", filters.invoiceType);
    qs.set("page", String(filters.page ?? 1));
    qs.set("page_size", String(filters.pageSize ?? 50));
    return apiClient.get<Page<SalesInvoice>>(`${BASE}/invoices?${qs.toString()}`, { companyId });
  },

  issueCreditNote: (companyId: string, branchId: string, invoiceId: string, reason: string, restock = true) =>
    apiClient.post<InvoiceIssueResponse>(
      `${BASE}/invoices/${invoiceId}:credit-note`,
      { reason, restock },
      { companyId, branchId }
    ),

  downloadInvoicePdf: (companyId: string, invoiceId: string, lang: string) =>
    apiClient.getBlob(`${BASE}/invoices/${invoiceId}/pdf?lang=${lang}`, { companyId }),

  sendInvoiceEmail: (companyId: string, invoiceId: string, toEmail?: string) =>
    apiClient.post<SalesInvoice>(
      `${BASE}/invoices/${invoiceId}:send-email`,
      { to_email: toEmail || undefined },
      { companyId }
    ),
};
