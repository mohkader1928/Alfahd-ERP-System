import { apiClient } from "@/lib/api-client";
import type { InvoiceIssueResponse, Quotation, QuotationLineIn, SalesOrder } from "./types";

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

  getSalesOrder: (companyId: string, id: string) => apiClient.get<SalesOrder>(`${BASE}/orders/${id}`, { companyId }),

  issueInvoice: (companyId: string, branchId: string, orderId: string) =>
    apiClient.post<InvoiceIssueResponse>(`${BASE}/orders/${orderId}:invoice`, undefined, { companyId, branchId }),

  getInvoice: (companyId: string, id: string) =>
    apiClient.get<InvoiceIssueResponse>(`${BASE}/invoices/${id}`, { companyId }),

  issueCreditNote: (companyId: string, branchId: string, invoiceId: string, reason: string) =>
    apiClient.post<InvoiceIssueResponse>(
      `${BASE}/invoices/${invoiceId}:credit-note`,
      { reason },
      { companyId, branchId }
    ),
};
