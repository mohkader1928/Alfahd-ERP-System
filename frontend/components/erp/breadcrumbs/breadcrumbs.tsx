import Link from "next/link";
import { ChevronRight, ChevronLeft } from "lucide-react";
import { useI18n } from "@/lib/i18n/config";

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

/**
 * Phase 17A standard breadcrumb trail (Part 8). Items are passed explicitly
 * by each screen rather than derived automatically from the URL — Next 16's
 * routing conventions differ enough from prior versions (see frontend's
 * AGENTS.md) that auto-deriving from segments would be guesswork; explicit
 * items are also the only way to show a record's *name* (not its UUID) as
 * the final crumb.
 */
export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  const { dir } = useI18n();
  const Separator = dir === "rtl" ? ChevronLeft : ChevronRight;

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-muted-foreground">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <span key={index} className="flex items-center gap-1">
            {index > 0 && <Separator className="h-3.5 w-3.5 shrink-0" />}
            {item.href && !isLast ? (
              <Link href={item.href} className="hover:text-foreground hover:underline underline-offset-4">
                {item.label}
              </Link>
            ) : (
              <span className={isLast ? "font-medium text-foreground" : undefined}>{item.label}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
