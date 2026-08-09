"use client";

import { useI18n } from "@/lib/i18n/config";
import { PaymentListView } from "@/features/payments/components/payment-list-view";

export default function PaymentsPage() {
  const { t } = useI18n();
  return <PaymentListView title={t("payments.title")} newHref="/payments/new" newLabel={t("payments.new")} />;
}
