"use client";

import { useI18n } from "@/lib/i18n/config";
import { PaymentFormView } from "@/features/payments/components/payment-form-view";

export default function NewPaymentPage() {
  const { t } = useI18n();
  return <PaymentFormView title={t("payments.create_title")} listLabel={t("payments.title")} listHref="/payments" />;
}
