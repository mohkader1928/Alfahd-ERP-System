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

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  const requestMutation = useMutation({
    mutationFn: () => identityApi.requestPasswordReset({ email }),
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    requestMutation.mutate();
  }

  if (requestMutation.isSuccess) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("auth.forgot_password.title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">{t("auth.forgot_password.success")}</p>
          <Link href="/reset-password">
            <Button className="w-full">{t("auth.forgot_password.link_continue")}</Button>
          </Link>
          <p className="text-center text-sm">
            <Link href="/login" className="text-muted-foreground underline underline-offset-4">
              {t("auth.forgot_password.link_back_to_login")}
            </Link>
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("auth.forgot_password.title")}</CardTitle>
        <CardDescription>{t("auth.forgot_password.subtitle")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">{t("auth.forgot_password.email")}</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={requestMutation.isPending}>
            {requestMutation.isPending ? t("common.loading") : t("auth.forgot_password.submit")}
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
