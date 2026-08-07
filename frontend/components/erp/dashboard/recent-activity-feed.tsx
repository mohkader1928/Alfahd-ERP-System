import Link from "next/link";
import { FileText, ShoppingCart, Wallet } from "lucide-react";
import { formatCurrency } from "@/lib/format-currency";
import { formatDate } from "@/lib/format-date";
import { sourceDocumentHref } from "@/lib/source-document-links";
import { useI18n } from "@/lib/i18n/config";
import type { RecentActivityItem } from "@/features/reporting/api/types";

const ICONS: Record<string, typeof FileText> = {
  sales_invoice: FileText,
  purchase_order: ShoppingCart,
  payment: Wallet,
};

export function RecentActivityFeed({ items }: { items: RecentActivityItem[] }) {
  const { t, locale } = useI18n();

  if (items.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">{t("dashboard.recent_activity.empty")}</p>;
  }

  return (
    <ul className="divide-y">
      {items.map((item) => {
        const Icon = ICONS[item.entity_type] ?? FileText;
        const href = sourceDocumentHref(item.entity_type, item.entity_id);
        const row = (
          <div className="flex items-center gap-3 py-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
              <Icon className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{item.label}</p>
              <p className="text-xs text-muted-foreground">{formatDate(item.date, locale)}</p>
            </div>
            <span className="text-sm font-medium tabular-nums">{formatCurrency(item.amount)}</span>
          </div>
        );
        return (
          <li key={`${item.entity_type}-${item.entity_id}`}>
            {href ? (
              <Link href={href} className="block hover:bg-accent/50 rounded-md -mx-2 px-2">
                {row}
              </Link>
            ) : (
              row
            )}
          </li>
        );
      })}
    </ul>
  );
}
