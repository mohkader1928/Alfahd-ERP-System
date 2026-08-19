import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";

interface KpiCardProps {
  label: string;
  value: string | undefined;
  isLoading?: boolean;
  isError?: boolean;
  href?: string;
  icon: LucideIcon;
  /** Tailwind classes for the icon chip's background + icon color, light
   * and dark. Hardening Sub-stage 1 (Owner: dashboard "not professional
   * enough"): each KPI gets its own fixed categorical accent (dataviz
   * skill slots 1-5, validated colorblind-safe) — never cycled/random,
   * so the same KPI always reads the same color. */
  accentClassName: string;
}

/**
 * Hardening Sub-stage 1 redesign: an icon chip in the KPI's fixed accent
 * color replaces the old flat gray card — the same numbers, but scannable
 * at a glance instead of five identical gray rectangles.
 */
export function KpiCard({ label, value, isLoading, isError, href, icon: Icon, accentClassName }: KpiCardProps) {
  const { t } = useI18n();
  const body = (
    <Card className={href ? "h-full transition-colors hover:bg-muted/40" : "h-full"}>
      <CardContent className="flex items-start gap-2 py-3">
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${accentClassName}`}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="truncate text-xs font-medium text-muted-foreground">{label}</p>
          {isLoading ? (
            <Skeleton className="h-5 w-20" />
          ) : isError ? (
            <p className="text-xs text-destructive">{t("common.error")}</p>
          ) : (
            <p className="truncate text-base font-semibold tabular-nums">{value}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}
