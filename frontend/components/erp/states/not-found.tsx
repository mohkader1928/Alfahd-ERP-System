import { FileQuestion } from "lucide-react";
import { useI18n } from "@/lib/i18n/config";

export function NotFoundState({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <FileQuestion className="h-8 w-8 text-muted-foreground" />
      <p className="text-sm font-medium">{label ?? t("common.not_found")}</p>
    </div>
  );
}
