"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n/config";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";

export default function ResetPasswordPage() {
  const { t } = useI18n();
  const [token, setToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const confirmMutation = useMutation({
    mutationFn: () => identityApi.confirmPasswordReset({ token: token.trim(), new_password: newPassword }),
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError(t("auth.reset_password.password_mismatch"));
      return;
    }
    confirmMutation.mutate();
  }

  if (confirmMutation.isSuccess) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("auth.reset_password.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">{t("auth.reset_password.success")}</p>
          <Link href="/login">
            <Button className="w-full">{t("auth.reset_password.link_login")}</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("auth.reset_password.title")}</CardTitle>
        <CardDescription>{t("auth.reset_password.subtitle")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="token">{t("auth.reset_password.token")}</Label>
            <Input
              id="token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-password">{t("auth.reset_password.new_password")}</Label>
            <Input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
            <p className="text-sm text-muted-foreground">{t("auth.reset_password.password_hint")}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm-password">{t("auth.reset_password.confirm_password")}</Label>
            <Input
              id="confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={confirmMutation.isPending}>
            {confirmMutation.isPending ? t("common.loading") : t("auth.reset_password.submit")}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm">
          <Link href="/login" className="text-muted-foreground underline underline-offset-4">
            {t("auth.forgot_password.link_back_to_login")}
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
