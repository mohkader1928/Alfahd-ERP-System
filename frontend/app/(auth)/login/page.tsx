"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n/config";
import { useAuthStore } from "@/stores/auth-store";
import { identityApi } from "@/features/identity/api/client";
import { decodeAccessToken, firstAuthorizedCompany } from "@/lib/jwt";
import { ApiError } from "@/lib/api-client";

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const setTokens = useAuthStore((s) => s.setTokens);
  const setActiveCompany = useAuthStore((s) => s.setActiveCompany);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [requires2fa, setRequires2fa] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: () => identityApi.login({ email, password }),
    onSuccess: (result) => {
      if ("requires_2fa" in result) {
        setRequires2fa(true);
        return;
      }
      applyTokens(result.access_token, result.refresh_token);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  const verify2faMutation = useMutation({
    mutationFn: () => identityApi.verify2fa({ email, password, totp_code: totpCode }),
    onSuccess: (result) => applyTokens(result.access_token, result.refresh_token),
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  function applyTokens(accessToken: string, refreshToken: string) {
    setTokens(accessToken, refreshToken);
    const authorizedCompanies = decodeAccessToken(accessToken)?.authorized_companies ?? [];
    // More than one company: no default is assumed — the picker decides,
    // never a silent [0] pick (docs/18-ui-ux-audit.md, finding B1).
    if (authorizedCompanies.length > 1) {
      router.push("/select-company");
      return;
    }
    const active = firstAuthorizedCompany(accessToken);
    if (active) setActiveCompany(active.companyId, active.branchId);
    router.push("/dashboard");
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (requires2fa) {
      verify2faMutation.mutate();
    } else {
      loginMutation.mutate();
    }
  }

  const pending = loginMutation.isPending || verify2faMutation.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("auth.login.title")}</CardTitle>
        <CardDescription>{t("app.name")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">{t("auth.login.email")}</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={requires2fa}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">{t("auth.login.password")}</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={requires2fa}
              required
            />
          </div>
          {requires2fa && (
            <div className="space-y-2">
              <Label htmlFor="totp">{t("auth.login.totp")}</Label>
              <Input
                id="totp"
                inputMode="numeric"
                maxLength={6}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                placeholder="000000"
                autoFocus
                required
              />
              <p className="text-sm text-muted-foreground">{t("auth.login.totp_hint")}</p>
            </div>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? t("common.loading") : t("auth.login.submit")}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm">
          <Link href="/setup" className="text-muted-foreground underline underline-offset-4">
            {t("auth.login.link_setup")}
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
