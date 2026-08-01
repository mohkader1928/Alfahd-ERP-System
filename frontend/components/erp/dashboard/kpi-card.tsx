import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/lib/i18n/config";

interface KpiCardProps {
  label: string;
  value: string | undefined;
  isLoading?: boolean;
  isError?: boolean;
  href?: string;
}

/**
 * Phase 17A dashboard KPI tile (Part 10). `href` is the drill-down link
 * ("view the records behind this number") — omit it for KPIs that have no
 * corresponding list screen yet rather than linking to a page that doesn't
 * exist.
 */
export function KpiCard({ label, value, isLoading, isError, href }: KpiCardProps) {
  const { t } = useI18n();
  const body = (
    <Card className={href ? "transition-colors hover:bg-muted/40" : undefined}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-8 w-32" />
        ) : isError ? (
          <p className="text-sm text-destructive">{t("common.error")}</p>
        ) : (
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
        )}
      </CardContent>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}
