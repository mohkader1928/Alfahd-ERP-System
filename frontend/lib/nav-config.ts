import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Banknote,
  BookUser,
  Boxes,
  Building2,
  Calculator,
  FileText,
  FolderTree,
  IdCard,
  LayoutDashboard,
  Package,
  Receipt,
  Ruler,
  Settings,
  ShieldCheck,
  ShoppingCart,
  Truck,
  Users,
} from "lucide-react";

export interface NavLink {
  type: "link";
  href: string;
  labelKey: string;
  icon: LucideIcon;
}

export interface NavGroup {
  type: "group";
  labelKey: string;
  icon: LucideIcon;
  children: NavLink[];
}

export type NavEntry = NavLink | NavGroup;

/**
 * Phase 17A navigation architecture (Part 1), extended in Phase 17B with a
 * real "Master Data" group. Config-driven so future phases add real pages
 * by appending an entry here, not by rewriting sidebar.tsx. Deliberately
 * does NOT include every item from the target ERP nav structure (Sales
 * Orders, Invoices, Sales Reports, General Ledger, an "Administration"
 * group for Companies/Users/Roles/Audit Log, etc.) — none of those have a
 * real page behind them yet, and fake nav entries with no destination are
 * explicitly prohibited. Every `href` below resolves to a real,
 * already-shipped page. As each target page lands in a later phase, add
 * its entry here (as a new child of an existing group, or a new group).
 *
 * The old flat "Administration → /admin" entry (Phase 17A) is retired in
 * 17B: its two sections (Partners, Products) are fully superseded by the
 * dedicated Master Data screens below.
 */
export const NAV_CONFIG: NavEntry[] = [
  { type: "link", href: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard },
  {
    type: "group",
    labelKey: "nav.sales",
    icon: ShoppingCart,
    children: [
      { type: "link", href: "/sales/quotations", labelKey: "nav.sales.quotations", icon: FileText },
      { type: "link", href: "/sales/orders", labelKey: "nav.sales.orders", icon: FileText },
      { type: "link", href: "/sales/invoices", labelKey: "nav.sales.invoices", icon: FileText },
      { type: "link", href: "/sales/receipts", labelKey: "sales.receipts.title", icon: Receipt },
      { type: "link", href: "/sales/reports", labelKey: "nav.sales.reports", icon: BarChart3 },
    ],
  },
  { type: "link", href: "/accounting", labelKey: "nav.accounting", icon: Calculator },
  { type: "link", href: "/inventory", labelKey: "nav.inventory", icon: Boxes },
  {
    type: "group",
    labelKey: "nav.purchasing",
    icon: Truck,
    children: [
      { type: "link", href: "/purchasing", labelKey: "nav.purchasing.orders_bills", icon: Truck },
      { type: "link", href: "/purchasing/payments", labelKey: "purchasing.payments.title", icon: Banknote },
      { type: "link", href: "/purchasing/reports", labelKey: "nav.purchasing.reports", icon: BarChart3 },
    ],
  },
  {
    type: "group",
    labelKey: "nav.master_data",
    icon: Package,
    children: [
      { type: "link", href: "/master-data/products", labelKey: "nav.master_data.products", icon: Package },
      { type: "link", href: "/master-data/categories", labelKey: "nav.master_data.categories", icon: FolderTree },
      { type: "link", href: "/master-data/uom", labelKey: "nav.master_data.uom", icon: Ruler },
      { type: "link", href: "/master-data/address-book", labelKey: "nav.master_data.address_book", icon: BookUser },
      { type: "link", href: "/master-data/customers", labelKey: "nav.master_data.customers", icon: Users },
      { type: "link", href: "/master-data/vendors", labelKey: "nav.master_data.vendors", icon: Building2 },
      { type: "link", href: "/master-data/employees", labelKey: "nav.master_data.employees", icon: IdCard },
    ],
  },
  {
    type: "group",
    labelKey: "settings.title",
    icon: Settings,
    children: [
      { type: "link", href: "/settings/company", labelKey: "settings.section.company", icon: Building2 },
      { type: "link", href: "/settings/security", labelKey: "settings.section.security", icon: ShieldCheck },
    ],
  },
];
