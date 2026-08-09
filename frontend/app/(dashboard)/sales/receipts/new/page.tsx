"use client";

import { useI18n } from "@/lib/i18n/config";
import { PaymentFormView } from "@/features/payments/components/payment-form-view";

export default function NewCustomerReceiptPage() {
  const { t } = useI18n();
  return (
    <PaymentFormView
      fixedType="customer"
      title={t("sales.receipts.create_title")}
      listLabel={t("sales.receipts.title")}
      listHref="/sales/receipts"
    />
  );
}
