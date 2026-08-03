import { apiClient } from "@/lib/api-client";
import type {
  AgingReport,
  DocumentBalance,
  Payment,
  PaymentCreateInput,
  PaymentDetail,
  PaymentType,
  Subledger,
} from "./types";

const BASE = "/api/v1/payments";

export const paymentsApi = {
  listPayments: (companyId: string, paymentType?: PaymentType) =>
    apiClient.get<Payment[]>(`${BASE}/payments${paymentType ? `?payment_type=${paymentType}` : ""}`, { companyId }),

  getPayment: (companyId: string, id: string) =>
    apiClient.get<PaymentDetail>(`${BASE}/payments/${id}`, { companyId }),

  createPayment: (companyId: string, branchId: string, payload: PaymentCreateInput) =>
    apiClient.post<Payment>(`${BASE}/payments`, payload, { companyId, branchId }),

  getSalesInvoiceBalance: (companyId: string, invoiceId: string) =>
    apiClient.get<DocumentBalance>(`${BASE}/balance/sales-invoice/${invoiceId}`, { companyId }),

  getVendorBillBalance: (companyId: string, billId: string) =>
    apiClient.get<DocumentBalance>(`${BASE}/balance/vendor-bill/${billId}`, { companyId }),

  customerSubledger: (companyId: string, partnerId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<Subledger>(
      `${BASE}/subledger/customer/${partnerId}?date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),

  vendorSubledger: (companyId: string, partnerId: string, dateFrom: string, dateTo: string) =>
    apiClient.get<Subledger>(
      `${BASE}/subledger/vendor/${partnerId}?date_from=${dateFrom}&date_to=${dateTo}`,
      { companyId }
    ),

  arAging: (companyId: string, asOfDate: string) =>
    apiClient.get<AgingReport>(`${BASE}/aging/ar?as_of_date=${asOfDate}`, { companyId }),

  apAging: (companyId: string, asOfDate: string) =>
    apiClient.get<AgingReport>(`${BASE}/aging/ap?as_of_date=${asOfDate}`, { companyId }),
};
