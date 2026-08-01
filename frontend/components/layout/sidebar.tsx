"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, ShoppingCart, Calculator, Boxes, Truck, Settings } from "lucide-react";
import { useI18n } from "@/lib/i18n/config";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { href: "/sales/quotations", labelKey: "nav.sales", icon: ShoppingCart },
  { href: "/accounting", labelKey: "nav.accounting", icon: Calculator },
  { href: "/inventory", labelKey: "nav.inventory", icon: Boxes },
  { href: "/purchasing", labelKey: "nav.purchasing", icon: Truck },
  { href: "/admin", labelKey: "nav.admin", icon: Settings },
];

export function Sidebar() {
  const { t } = useI18n();
  const pathname = usePathname();

  return (
    <aside className="hidden w-60 shrink-0 border-e bg-sidebar text-sidebar-foreground md:block">
      <div className="flex h-14 items-center border-b px-4 font-semibold">{t("app.name")}</div>
      <nav className="space-y-1 p-2">
        {NAV_ITEMS.map(({ href, labelKey, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {t(labelKey)}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
