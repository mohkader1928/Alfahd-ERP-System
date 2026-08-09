"use client";

import { useI18n } from "@/lib/i18n/config";
import { PaymentFormView } from "@/features/payments/components/payment-form-view";

export default function NewVendorPaymentPage() {
  const { t } = useI18n();
  return (
    <PaymentFormView
      fixedType="vendor"
      title={t("purchasing.payments.create_title")}
      listLabel={t("purchasing.payments.title")}
      listHref="/purchasing/payments"
    />
  );
}
