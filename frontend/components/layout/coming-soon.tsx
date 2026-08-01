"use client";

import { useI18n } from "@/lib/i18n/config";

export function ComingSoon({ title }: { title: string }) {
  const { t } = useI18n();
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="text-muted-foreground">{t("common.coming_soon")}</p>
    </div>
  );
}
