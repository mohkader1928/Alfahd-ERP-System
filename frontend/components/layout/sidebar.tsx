"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown } from "lucide-react";
import { NAV_CONFIG, type NavGroup, type NavLink } from "@/lib/nav-config";
import { useI18n } from "@/lib/i18n/config";
import { useMyPermissions } from "@/hooks/use-permissions";
import { cn } from "@/lib/utils";

function isLinkActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinkItem({
  item,
  pathname,
  indent,
  iconColor,
}: {
  item: NavLink;
  pathname: string;
  indent?: boolean;
  /** Owner request: a child link inside a group now takes on its
   * parent module's own color (passed down by NavGroupItem below) so
   * "دليل الحسابات" reads violet right alongside "المحاسبة" itself —
   * one color per module, not a rainbow of unrelated per-item colors.
   * Falls back to the item's own iconColor for the few top-level links
   * (Dashboard) that aren't inside a group at all. */
  iconColor?: string;
}) {
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
      <Icon className={cn("h-4 w-4 shrink-0", iconColor ?? item.iconColor)} />
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
        <Icon className={cn("h-4 w-4 shrink-0", group.iconColor)} />
        <span className="flex-1 text-start">{t(group.labelKey)}</span>
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-1 py-1">
          {group.children.map((child) => (
            <NavLinkItem key={child.href} item={child} pathname={pathname} indent iconColor={group.iconColor} />
          ))}
        </div>
      )}
    </div>
  );
}

export function Sidebar() {
  const { t } = useI18n();
  const pathname = usePathname();
  // Hardening Issue #5: the sidebar previously showed every nav item to
  // every user regardless of RBAC permissions, unlike the rest of the app
  // which already hides unauthorized actions via <Can> rather than merely
  // disabling them. Filtering here (not disabling) matches that established
  // convention and keeps items the user isn't authorized for out of the
  // menu entirely, hiding groups that end up with no visible children.
  const { can, canAny, isLoading } = useMyPermissions();

  function isVisible(item: NavLink): boolean {
    if (!item.permission) return true;
    if (isLoading) return false;
    return Array.isArray(item.permission) ? canAny(item.permission) : can(item.permission);
  }

  return (
    <aside className="hidden w-60 shrink-0 border-e bg-sidebar text-sidebar-foreground md:block">
      <div className="flex h-14 items-center border-b px-4 font-semibold">{t("app.name")}</div>
      <nav className="space-y-1 p-2">
        {NAV_CONFIG.map((entry) => {
          if (entry.type === "link") {
            return isVisible(entry) ? <NavLinkItem key={entry.href} item={entry} pathname={pathname} /> : null;
          }
          const visibleChildren = entry.children.filter(isVisible);
          if (visibleChildren.length === 0) return null;
          return (
            <NavGroupItem key={entry.labelKey} group={{ ...entry, children: visibleChildren }} pathname={pathname} />
          );
        })}
      </nav>
    </aside>
  );
}
