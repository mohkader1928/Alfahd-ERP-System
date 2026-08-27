"use client";

import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/lib/i18n/config";
import { accountingApi } from "@/features/accounting/api/client";
import { formatCurrency } from "@/lib/format-currency";
import type { Account } from "@/features/accounting/api/types";

const DEBIT_NORMAL_TYPES = new Set(["asset", "expense"]);

/**
 * Owner request: on any screen that records a GL account against an
 * amount (Journal Entry lines, Payments/Customer Receipts/Vendor
 * Payments), show the selected account's current balance and flag it
 * (color only, never blocking) when the balance already contradicts the
 * account's own debit-normal/credit-normal nature -- e.g. a credit
 * balance on a bank (asset) account. Same debit-normal classification the
 * Income Statement route already applies server-side (no contra-account
 * exception, matching that existing behavior exactly). "Current balance"
 * is posted-only, matching every other balance figure in this app.
 */
export function AccountBalanceHint({ companyId, account }: { companyId: string; account: Account | undefined }) {
  const { t } = useI18n();
  const balanceQuery = useQuery({
    queryKey: ["account-balance", companyId, account?.id],
    queryFn: () => accountingApi.getAccountBalance(companyId, account!.id),
    enabled: !!account,
  });

  if (!account) return null;
  if (balanceQuery.isLoading || !balanceQuery.data) {
    return <p className="text-xs text-muted-foreground">{t("common.loading")}</p>;
  }

  const balance = Number(balanceQuery.data.balance);
  const isDebitNormal = DEBIT_NORMAL_TYPES.has(account.account_type_code);
  const abnormal = (isDebitNormal && balance < 0) || (!isDebitNormal && balance > 0);
  const side = balance > 0 ? t("accounting.balance_hint.debit") : balance < 0 ? t("accounting.balance_hint.credit") : null;

  return (
    <p className={`text-xs ${abnormal ? "font-medium text-destructive" : "text-muted-foreground"}`}>
      {t("accounting.balance_hint.current_balance")}: {formatCurrency(Math.abs(balance))}
      {side ? ` (${side})` : ""}
      {abnormal ? ` — ${t("accounting.balance_hint.abnormal")}` : ""}
    </p>
  );
}
