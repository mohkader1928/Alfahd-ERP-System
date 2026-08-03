"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import { Building2, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { Breadcrumbs } from "@/components/erp/breadcrumbs/breadcrumbs";
import { useI18n } from "@/lib/i18n/config";

interface SettingsSection {
  href: string;
  labelKey: string;
  icon: LucideIcon;
}

/**
 * Settings Architecture Foundation milestone. Every settings area (Company
 * today; Sales/Purchasing/Inventory/Accounting/Payments module settings
 * later) renders inside this one shell instead of each becoming its own
 * ad hoc page layout — the section list below is the only thing a future
 * settings area needs to extend. Deliberately only lists sections that
 * have a real page behind them today (same "no fake nav entries" rule
 * nav-config.ts already documents) — Sales/Purchasing/... settings are not
 * listed here until they exist.
 */
const SETTINGS_SECTIONS: SettingsSection[] = [
  { href: "/settings/company", labelKey: "settings.section.company", icon: Building2 },
  { href: "/settings/security", labelKey: "settings.section.security", icon: ShieldCheck },
];

export function SettingsShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();

  return (
    <div className="space-y-4">
      <Breadcrumbs items={[{ label: t("settings.title") }]} />
      <h1 className="text-2xl font-semibold">{t("settings.title")}</h1>

      <div className="flex flex-col gap-6 sm:flex-row">
        <nav className="flex shrink-0 gap-1 overflow-x-auto sm:w-48 sm:flex-col sm:overflow-visible">
          {SETTINGS_SECTIONS.map((section) => {
            const isActive = pathname?.startsWith(section.href);
            const Icon = section.icon;
            return (
              <Link
                key={section.href}
                href={section.href}
                className={cn(
                  "flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {t(section.labelKey)}
              </Link>
            );
          })}
        </nav>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
