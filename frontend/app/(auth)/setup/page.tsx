"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/lib/i18n/config";
import { identityApi } from "@/features/identity/api/client";
import { ApiError } from "@/lib/api-client";
import type { BootstrapRequest } from "@/features/identity/api/types";

const initialForm: BootstrapRequest = {
  tenant_legal_name: "",
  company_legal_name: "",
  company_legal_name_ar: "",
  vat_number: "",
  base_currency_code: "SAR",
  valuation_method: "average",
  admin_email: "",
  admin_full_name: "",
  admin_password: "",
};

const VALUATION_METHOD_LABELS: Record<string, string> = {
  average: "Average Cost",
  fifo: "FIFO",
};

export default function SetupPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [form, setForm] = useState<BootstrapRequest>(initialForm);
  const [error, setError] = useState<string | null>(null);

  const bootstrapMutation = useMutation({
    mutationFn: () => identityApi.bootstrap(form),
    onSuccess: () => router.push("/login"),
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("common.error")),
  });

  function update<K extends keyof BootstrapRequest>(key: K, value: BootstrapRequest[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    bootstrapMutation.mutate();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("setup.title")}</CardTitle>
        <CardDescription>{t("setup.subtitle")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>{t("setup.tenant_name")}</Label>
            <Input value={form.tenant_legal_name} onChange={(e) => update("tenant_legal_name", e.target.value)} required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>{t("setup.company_name")}</Label>
              <Input value={form.company_legal_name} onChange={(e) => update("company_legal_name", e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label>{t("setup.company_name_ar")}</Label>
              <Input value={form.company_legal_name_ar} onChange={(e) => update("company_legal_name_ar", e.target.value)} required dir="rtl" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>{t("setup.vat_number")}</Label>
              <Input
                value={form.vat_number}
                onChange={(e) => update("vat_number", e.target.value)}
                maxLength={15}
                pattern="\d{15}"
                required
              />
            </div>
            <div className="space-y-2">
              <Label>{t("setup.valuation_method")}</Label>
              <Select value={form.valuation_method} onValueChange={(v) => update("valuation_method", v as "fifo" | "average")}>
                <SelectTrigger>
                  {/* Base UI's Select.Value shows the raw value by default,
                      not the matching SelectItem's label — see the same note
                      on the quotation form's customer/product selects. */}
                  <SelectValue>
                    {(value: string) => (VALUATION_METHOD_LABELS[value] ?? value)}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="average">Average Cost</SelectItem>
                  <SelectItem value="fifo">FIFO</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label>{t("setup.admin_name")}</Label>
            <Input value={form.admin_full_name} onChange={(e) => update("admin_full_name", e.target.value)} required />
          </div>
          <div className="space-y-2">
            <Label>{t("setup.admin_email")}</Label>
            <Input type="email" value={form.admin_email} onChange={(e) => update("admin_email", e.target.value)} required />
          </div>
          <div className="space-y-2">
            <Label>{t("setup.admin_password")}</Label>
            <Input
              type="password"
              value={form.admin_password}
              onChange={(e) => update("admin_password", e.target.value)}
              minLength={10}
              required
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={bootstrapMutation.isPending}>
            {bootstrapMutation.isPending ? t("common.loading") : t("setup.submit")}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm">
          <Link href="/login" className="text-muted-foreground underline underline-offset-4">
            {t("setup.link_login")}
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
