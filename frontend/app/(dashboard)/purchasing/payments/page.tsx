"use client";

import { useI18n } from "@/lib/i18n/config";
import { PaymentListView } from "@/features/payments/components/payment-list-view";

export default function VendorPaymentsPage() {
  const { t } = useI18n();
  return (
    <PaymentListView
      paymentType="vendor"
      title={t("purchasing.payments.title")}
      newHref="/purchasing/payments/new"
      newLabel={t("purchasing.payments.new")}
    />
  );
}
