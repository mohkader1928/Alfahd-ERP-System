"use client";

import { useI18n } from "@/lib/i18n/config";
import { PaymentListView } from "@/features/payments/components/payment-list-view";

export default function CustomerReceiptsPage() {
  const { t } = useI18n();
  return (
    <PaymentListView
      paymentType="customer"
      title={t("sales.receipts.title")}
      newHref="/sales/receipts/new"
      newLabel={t("sales.receipts.new")}
    />
  );
}
