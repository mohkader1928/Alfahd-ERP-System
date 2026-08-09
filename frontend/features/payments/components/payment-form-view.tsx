"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormView } from "@/components/erp/form-view/form-view";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { accountingApi } from "@/features/accounting/api/client";
import { salesApi } from "@/features/sales/api/client";
import { purchasingApi } from "@/features/purchasing/api/client";
import { paymentsApi } from "@/features/payments/api/client";
import type { PaymentType } from "@/features/payments/api/types";
import { ApiError } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format-currency";
import { toastError, toastSuccess } from "@/lib/toast";

// Owner directive: customer receipts and vendor payments are separate
// documents now (own module, own number sequence -- see the migration
// splitting Payment.number into RCT-/PAY- series). When `fixedType` is
// set, the type is implied by which screen you're on (no selector, no
// reset-on-type-change) -- the /payments/new fallback keeps the
// original type selector for the one still-generic entry point (the
// Dashboard's quick action).
export function PaymentFormView({
  fixedType,
  title,
  listLabel,
  listHref,
}: {
  fixedType?: PaymentType;
  title: string;
  listLabel: string;
  listHref: string;
}) {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const branchId = useAuthStore((s) => s.activeBranchId)!;

  const [paymentType, setPaymentType] = useState<PaymentType>(fixedType ?? "customer");
  const [partnerId, setPartnerId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [paymentDate, setPaymentDate] = useState(() => new Date().toISOString().slice(0, 10));
  // null means "not yet touched by the user" — the input then displays the
  // selected document's outstanding balance as a default, without needing
  // an effect to sync the two: selecting a new document naturally shows
  // its own balance again the moment the override is cleared.
  const [amountOverride, setAmountOverride] = useState<string | null>(null);
  const [accountId, setAccountId] = useState("");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);

  const partnersQuery = useQuery({
    queryKey: ["partners", companyId, paymentType],
    queryFn: () =>
      identityApi.listPartners(companyId, branchId, {
        customersOnly: paymentType === "customer",
        vendorsOnly: paymentType === "vendor",
      }),
  });
  const accountsQuery = useQuery({
    queryKey: ["accounts", companyId],
    queryFn: () => accountingApi.listAccounts(companyId),
  });

  const invoicesQuery = useQuery({
    queryKey: ["sales-invoices", companyId, partnerId],
    queryFn: () => salesApi.listInvoices(companyId, { partnerId, pageSize: 200 }),
    enabled: paymentType === "customer" && !!partnerId,
  });
  const billsQuery = useQuery({
    queryKey: ["vendor-bills", companyId, partnerId],
    queryFn: () => purchasingApi.listVendorBills(companyId, { partnerId, pageSize: 200 }),
    enabled: paymentType === "vendor" && !!partnerId,
  });
  const documents = paymentType === "customer" ? invoicesQuery.data?.items : billsQuery.data?.items;

  const balanceQuery = useQuery({
    queryKey: ["document-balance", companyId, paymentType, targetId],
    queryFn: () =>
      paymentType === "customer"
        ? paymentsApi.getSalesInvoiceBalance(companyId, targetId)
        : paymentsApi.getVendorBillBalance(companyId, targetId),
    enabled: !!targetId,
  });

  const amount = amountOverride ?? balanceQuery.data?.balance_due ?? "0.00";

  const createMutation = useMutation({
    mutationFn: () =>
      paymentsApi.createPayment(companyId, branchId, {
        partner_id: partnerId,
        payment_type: paymentType,
        payment_date: paymentDate,
        amount,
        account_id: accountId,
        reference: reference || undefined,
        allocations: targetId
          ? [
              {
                sales_invoice_id: paymentType === "customer" ? targetId : null,
                vendor_bill_id: paymentType === "vendor" ? targetId : null,
                amount,
              },
            ]
          : [],
      }),
    onSuccess: (payment) => {
      queryClient.invalidateQueries({ queryKey: ["payments", companyId] });
      toastSuccess(t("toast.success_title"), payment.number);
      router.push(listHref);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setError(detail);
      toastError(t("toast.error_title"), detail);
    },
  });

  return (
    <FormView
      title={title}
      breadcrumbs={[{ label: listLabel, href: listHref }, { label: title }]}
      onSave={() => {
        setError(null);
        createMutation.mutate();
      }}
      onCancel={() => router.push(listHref)}
      isSaving={createMutation.isPending}
      saveDisabled={!partnerId || !accountId || !amount}
      error={error}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {!fixedType && (
          <div className="space-y-1">
            <Label>{t("payments.type")}</Label>
            <Select
              value={paymentType}
              onValueChange={(v) => {
                setPaymentType((v ?? "customer") as PaymentType);
                setPartnerId("");
                setTargetId("");
                setAmountOverride(null);
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="customer">{t("payments.type.customer")}</SelectItem>
                <SelectItem value="vendor">{t("payments.type.vendor")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="space-y-1">
          <Label>{t("payments.select_partner")}</Label>
          <Select
            value={partnerId}
            onValueChange={(v) => {
              setPartnerId(v ?? "");
              setTargetId("");
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t("payments.select_partner")}>
                {(v: string) => partnersQuery.data?.find((p) => p.id === v)?.name ?? v}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {partnersQuery.data?.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1 sm:col-span-2">
          <Label>{t("payments.select_document")}</Label>
          <Select
            value={targetId}
            onValueChange={(v) => {
              setTargetId(v ?? "");
              setAmountOverride(null);
            }}
            disabled={!partnerId}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={partnerId ? t("payments.select_document") : t("payments.select_partner_first")}>
                {(v: string) => {
                  const doc = documents?.find((d) => d.id === v);
                  return doc ? `${doc.number} — ${formatCurrency(doc.total_amount)}` : v;
                }}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {documents?.map((doc) => (
                <SelectItem key={doc.id} value={doc.id}>
                  {doc.number} — {formatCurrency(doc.total_amount)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {balanceQuery.data && (
            <p className="text-muted-foreground text-xs">
              {t("payments.outstanding_balance")}: {formatCurrency(balanceQuery.data.balance_due)} (
              {t(`payments.status.${balanceQuery.data.payment_status}`)})
            </p>
          )}
        </div>
        <div className="space-y-1">
          <Label>{t("payments.date")}</Label>
          <Input type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label>{t("payments.amount")}</Label>
          <Input value={amount} onChange={(e) => setAmountOverride(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label>{t("payments.select_account")}</Label>
          <Select value={accountId} onValueChange={(v) => setAccountId(v ?? "")}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t("payments.select_account")} />
            </SelectTrigger>
            <SelectContent>
              {accountsQuery.data?.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  {a.code} — {a.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>{t("payments.reference")}</Label>
          <Input value={reference} onChange={(e) => setReference(e.target.value)} />
        </div>
      </div>
    </FormView>
  );
}
