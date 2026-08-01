import { ShieldAlert } from "lucide-react";
import { useI18n } from "@/lib/i18n/config";

export function PermissionDenied() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <ShieldAlert className="h-8 w-8 text-muted-foreground" />
      <p className="text-sm font-medium">{t("common.permission_denied")}</p>
      <p className="max-w-sm text-sm text-muted-foreground">{t("common.permission_denied_hint")}</p>
    </div>
  );
}
