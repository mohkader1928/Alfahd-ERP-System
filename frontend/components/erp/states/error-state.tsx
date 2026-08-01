import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/config";

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <AlertTriangle className="h-8 w-8 text-destructive" />
      <p className="text-sm font-medium text-destructive">{message ?? t("common.error")}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-2">
          <RefreshCw className="h-4 w-4" />
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}
