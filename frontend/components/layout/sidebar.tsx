"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { NAV_CONFIG, type NavGroup, type NavLink } from "@/lib/nav-config";
import { useI18n } from "@/lib/i18n/config";
import { cn } from "@/lib/utils";

function isLinkActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinkItem({ item, pathname, indent }: { item: NavLink; pathname: string; indent?: boolean }) {
  const { t } = useI18n();
  const active = isLinkActive(pathname, item.href);
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={cn(
        "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        indent && "ps-8",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
      )}
    >
      <Icon className="h-4 w-4" />
      {t(item.labelKey)}
    </Link>
  );
}

function NavGroupItem({ group, pathname }: { group: NavGroup; pathname: string }) {
  const { t } = useI18n();
  const groupActive = group.children.some((c) => isLinkActive(pathname, c.href));
  // Groups default open when they contain the active route, or when the
  // nav is this small (Phase 17A: at most one group, one child) — always
  // starting expanded avoids a pointless extra click for now, while the
  // toggle itself is ready for when a group grows past a couple of items.
  const [open, setOpen] = useState(true);
  const Icon = group.icon;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={cn(
          "flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          groupActive
            ? "text-sidebar-accent-foreground"
            : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        )}
      >
        <Icon className="h-4 w-4" />
        <span className="flex-1 text-start">{t(group.labelKey)}</span>
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-1 py-1">
          {group.children.map((child) => (
            <NavLinkItem key={child.href} item={child} pathname={pathname} indent />
          ))}
        </div>
      )}
    </div>
  );
}

export function Sidebar() {
  const { t } = useI18n();
  const pathname = usePathname();

  return (
    <aside className="hidden w-60 shrink-0 border-e bg-sidebar text-sidebar-foreground md:block">
      <div className="flex h-14 items-center border-b px-4 font-semibold">{t("app.name")}</div>
      <nav className="space-y-1 p-2">
        {NAV_CONFIG.map((entry) =>
          entry.type === "link" ? (
            <NavLinkItem key={entry.href} item={entry} pathname={pathname} />
          ) : (
            <NavGroupItem key={entry.labelKey} group={entry} pathname={pathname} />
          )
        )}
      </nav>
    </aside>
  );
}
