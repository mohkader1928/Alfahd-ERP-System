"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SettingsShell } from "@/components/erp/settings-shell/settings-shell";
import { FormView } from "@/components/erp/form-view/form-view";
import { PermissionDenied } from "@/components/erp/states/permission-denied";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";
import { useMyPermissions } from "@/hooks/use-permissions";
import { useAuthStore } from "@/stores/auth-store";
import { accountingApi } from "@/features/accounting/api/client";
import { ApiError } from "@/lib/api-client";
import { toastSuccess } from "@/lib/toast";
import type { Account } from "@/features/accounting/api/types";

/**
 * INV-002 — Accounting Settings. Currently a single field: the account
 * Cycle Count approval posts inventory shortage/surplus adjustments to.
 * Previously hardcoded as account code "5200" ("Operating Expenses"),
 * which broke in production the moment a company added a sub-account
 * under it (an ordinary bookkeeping action that silently turns it into a
 * group account). Deliberately minimal per Owner directive: one
 * configurable account, not a general settings framework -- other
 * modules' hardcoded posting accounts are tracked separately as
 * ACC-CONFIG-001, not addressed here.
 */
export default function AccountingSettingsPage() {
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const { can } = useMyPermissions();
  const canManage = can("accounting.settings.manage");

  const settingsQuery = useQuery({
    queryKey: ["accounting-settings", companyId],
    queryFn: () => accountingApi.getSettings(companyId),
    enabled: canManage,
  });

  const accountsQuery = useQuery({
    queryKey: ["accounts", companyId],
    queryFn: () => accountingApi.listAccounts(companyId),
    enabled: canManage,
  });

  if (!canManage) {
    return (
      <SettingsShell>
        <PermissionDenied />
      </SettingsShell>
    );
  }

  if (settingsQuery.isLoading || !settingsQuery.data || accountsQuery.isLoading || !accountsQuery.data) {
    return (
      <SettingsShell>
        <Skeleton className="h-48 w-full" />
      </SettingsShell>
    );
  }

  return (
    <SettingsShell>
      <AccountingSettingsForm
        companyId={companyId}
        inventoryAdjustmentAccountId={settingsQuery.data.inventory_adjustment_account_id}
        accounts={accountsQuery.data}
      />
    </SettingsShell>
  );
}

function AccountingSettingsForm({
  companyId,
  inventoryAdjustmentAccountId,
  accounts,
}: {
  companyId: string;
  inventoryAdjustmentAccountId: string | null;
  accounts: Account[];
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string | null>(inventoryAdjustmentAccountId);
  const [error, setError] = useState<string | null>(null);

  // Only detailed expense accounts are valid choices -- matches the
  // backend's own validation (AccountingSettingsService, not-a-group +
  // expense-type) exactly, so a user can never even select an account the
  // server would reject.
  const postingExpenseAccounts = accounts.filter((a) => !a.is_group && a.account_type_code === "expense");

  const saveMutation = useMutation({
    mutationFn: () =>
      accountingApi.updateSettings(companyId, { inventory_adjustment_account_id: selected }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounting-settings", companyId] });
      toastSuccess(t("toast.success_title"), t("settings.accounting.saved"));
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  return (
    <FormView
      title={t("settings.section.accounting")}
      onSave={() => {
        setError(null);
        saveMutation.mutate();
      }}
      isSaving={saveMutation.isPending}
      error={error}
    >
      <div className="space-y-1 max-w-md">
        <Label>{t("settings.accounting.inventory_adjustment_account")}</Label>
        <Select value={selected ?? "__none__"} onValueChange={(v) => setSelected(v === "__none__" ? null : v)}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="—">
              {(v: string) => {
                const acc = postingExpenseAccounts.find((a) => a.id === v);
                return acc ? `${acc.code} — ${acc.name}` : "—";
              }}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">—</SelectItem>
            {postingExpenseAccounts.map((a) => (
              <SelectItem key={a.id} value={a.id}>
                {a.code} — {a.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          {t("settings.accounting.inventory_adjustment_account_hint")}
        </p>
      </div>
    </FormView>
  );
}
