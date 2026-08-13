"use client";

import { useState } from "react";
import QRCode from "react-qr-code";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SettingsShell } from "@/components/erp/settings-shell/settings-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import { toastError, toastSuccess } from "@/lib/toast";

/**
 * P0-3 (Phase-One audit closure) — the TOTP verification half
 * (login's 2FA challenge screen) already existed and worked; this is the
 * missing other half — the only place a user can actually turn 2FA on.
 * No settings/"My Account" page existed at all before this, so it's a
 * new SettingsShell section rather than an addition to an existing one.
 *
 * State machine, matching the backend exactly: `not_enrolled` (2FA off,
 * nothing started) -> `enrolling` (secret/QR fetched, not yet verified —
 * `is_2fa_enabled` is still false server-side at this point, proven by
 * the P0-3 test suite) -> `enabled` (verified, secret no longer shown).
 * A failed code keeps the user in `enrolling` with an inline error —
 * opening the screen or fetching the QR never flips the flag; only a
 * correct code does.
 */
export default function AccountSettingsPage() {
  const { t } = useI18n();
  const companyId = useAuthStore((s) => s.activeCompanyId)!;
  const queryClient = useQueryClient();

  const [setupInfo, setSetupInfo] = useState<{ secret: string; provisioning_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const profileQuery = useQuery({
    queryKey: ["my-profile", companyId],
    queryFn: () => identityApi.getMyProfile(companyId),
  });

  const startMutation = useMutation({
    mutationFn: () => identityApi.start2faEnrollment(companyId),
    onSuccess: (data) => {
      setSetupInfo(data);
      setVerifyError(null);
      setCode("");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      toastError(t("toast.error_title"), detail);
    },
  });

  const verifyMutation = useMutation({
    mutationFn: () => identityApi.verify2faEnrollment(companyId, code),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["my-profile", companyId] });
      toastSuccess(t("toast.success_title"), t("settings.account.2fa_enabled_toast"));
      // Never keep the secret in memory once enrollment is actually done.
      setSetupInfo(null);
      setCode("");
      setVerifyError(null);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : t("common.error");
      setVerifyError(detail);
    },
  });

  if (profileQuery.isLoading || !profileQuery.data) {
    return (
      <SettingsShell>
        <Skeleton className="h-64 w-full" />
      </SettingsShell>
    );
  }

  const is2faEnabled = profileQuery.data.is_2fa_enabled;

  return (
    <SettingsShell>
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.account.2fa_title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">{t("settings.account.2fa_status")}</span>
            <Badge variant={is2faEnabled ? "default" : "outline"}>
              {is2faEnabled ? t("settings.account.2fa_status_enabled") : t("settings.account.2fa_status_disabled")}
            </Badge>
          </div>

          {is2faEnabled && !setupInfo && (
            <p className="text-sm text-muted-foreground">{t("settings.account.2fa_already_enabled_hint")}</p>
          )}

          {!is2faEnabled && !setupInfo && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">{t("settings.account.2fa_disabled_hint")}</p>
              <Button size="sm" onClick={() => startMutation.mutate()} disabled={startMutation.isPending}>
                {startMutation.isPending ? t("common.loading") : t("settings.account.2fa_start")}
              </Button>
            </div>
          )}

          {setupInfo && (
            <div className="space-y-4 rounded-lg border p-4">
              <div className="space-y-2">
                <p className="text-sm font-medium">{t("settings.account.2fa_scan_hint")}</p>
                <div className="w-fit rounded-md bg-white p-3">
                  <QRCode value={setupInfo.provisioning_uri} size={160} />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("settings.account.2fa_manual_secret")}</Label>
                <code className="block w-fit rounded bg-muted px-2 py-1 font-mono text-sm tracking-wider">
                  {setupInfo.secret}
                </code>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t("settings.account.2fa_code_label")}</Label>
                <div className="flex items-end gap-2">
                  <Input
                    value={code}
                    onChange={(e) => {
                      setCode(e.target.value);
                      setVerifyError(null);
                    }}
                    placeholder={t("settings.account.2fa_code_placeholder")}
                    className="w-40"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                  />
                  <Button
                    size="sm"
                    onClick={() => verifyMutation.mutate()}
                    disabled={!code || verifyMutation.isPending}
                  >
                    {verifyMutation.isPending ? t("common.loading") : t("settings.account.2fa_verify")}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setSetupInfo(null);
                      setCode("");
                      setVerifyError(null);
                    }}
                  >
                    {t("common.cancel")}
                  </Button>
                </div>
                {verifyError && <p className="text-sm text-destructive">{verifyError}</p>}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </SettingsShell>
  );
}
