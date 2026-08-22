import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  ArrowLeftRight,
  BarChart3,
  Banknote,
  BookOpen,
  BookUser,
  Boxes,
  Building2,
  Calculator,
  ClipboardCheck,
  ClipboardList,
  Coins,
  FileSpreadsheet,
  FileText,
  FolderTree,
  IdCard,
  Landmark,
  LayoutDashboard,
  Lock,
  Package,
  PackageSearch,
  PieChart,
  Receipt,
  Ruler,
  Scale,
  Settings,
  ShieldCheck,
  ShoppingCart,
  TrendingUp,
  Truck,
  Undo2,
  UserCog,
  Users,
  Warehouse,
} from "lucide-react";

export interface NavLink {
  type: "link";
  href: string;
  labelKey: string;
  icon: LucideIcon;
  /**
   * Owner request: each top-level module reads as its own colored "app"
   * in the sidebar (Sales, Accounting, Inventory, Purchasing, ...)
   * instead of every icon sharing one muted gray — a fixed Tailwind text-
   * color class, deliberately theme-independent (this app's own accent
   * hue is user-selectable via the "app color" picker, so a per-module
   * identity color has to survive every one of those choices rather than
   * being derived from a theme token). Only ever set on a top-level entry
   * (the Dashboard link itself, and each NavGroup below) — a child link
   * inside a group intentionally has no color of its own, so the module's
   * identity reads once at the group header, not once per line.
   */
  iconColor?: string;
  /**
   * Hardening Issue #5: the permission code(s) gating the page this link
   * leads to (matching the underlying list endpoint's own
   * `require_permission(...)`). A link with no `permission` is always
   * shown — reserved for self-service screens like /settings/account that
   * every authenticated user can reach regardless of RBAC role. An array
   * means any one of the codes grants visibility (mirrors `<Can>`'s
   * `canAny`).
   */
  permission?: string | string[];
}

export interface NavGroup {
  type: "group";
  labelKey: string;
  icon: LucideIcon;
  /** See NavLink.iconColor — same theme-independent per-module color, applied to this group's own header icon. */
  iconColor?: string;
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
  {
    type: "link",
    href: "/dashboard",
    labelKey: "nav.dashboard",
    icon: LayoutDashboard,
    iconColor: "text-blue-600",
    permission: "reporting.dashboard.view",
  },
  {
    type: "group",
    labelKey: "nav.sales",
    icon: ShoppingCart,
    iconColor: "text-emerald-600",
    children: [
      { type: "link", href: "/sales/quotations", labelKey: "nav.sales.quotations", icon: FileText, permission: "sales.quotation.create" },
      { type: "link", href: "/sales/orders", labelKey: "nav.sales.orders", icon: FileText, permission: "sales.order.view" },
      { type: "link", href: "/sales/invoices", labelKey: "nav.sales.invoices", icon: FileText, permission: "sales.invoice.create" },
      { type: "link", href: "/sales/returns", labelKey: "nav.sales.returns", icon: Undo2, permission: "sales.invoice.create" },
      { type: "link", href: "/sales/receipts", labelKey: "sales.receipts.title", icon: Receipt, permission: "payment.view" },
      { type: "link", href: "/sales/reports", labelKey: "nav.sales.reports", icon: BarChart3, permission: "reporting.sales.view" },
    ],
  },
  {
    type: "group",
    labelKey: "nav.accounting",
    icon: Calculator,
    iconColor: "text-violet-600",
    children: [
      { type: "link", href: "/accounting?tab=accounts", labelKey: "accounting.tabs.accounts", icon: BookOpen, permission: "accounting.chart_of_accounts.view" },
      {
        type: "link",
        href: "/accounting?tab=journal-entries",
        labelKey: "accounting.tabs.journal_entries",
        icon: ClipboardList,
        permission: "accounting.journal_entry.view",
      },
      {
        type: "link",
        href: "/accounting?tab=trial-balance",
        labelKey: "accounting.tabs.trial_balance",
        icon: Scale,
        permission: "accounting.reports.trial_balance.view",
      },
      {
        type: "link",
        href: "/accounting?tab=income-statement",
        labelKey: "accounting.tabs.income_statement",
        icon: TrendingUp,
        permission: "accounting.reports.income_statement.view",
      },
      {
        type: "link",
        href: "/accounting?tab=balance-sheet",
        labelKey: "accounting.tabs.balance_sheet",
        icon: FileSpreadsheet,
        permission: "accounting.reports.balance_sheet.view",
      },
      {
        type: "link",
        href: "/accounting?tab=cash-flow",
        labelKey: "accounting.tabs.cash_flow",
        icon: Banknote,
        permission: "accounting.reports.cash_flow.view",
      },
      {
        type: "link",
        href: "/accounting?tab=equity-statement",
        labelKey: "accounting.tabs.equity_statement",
        icon: PieChart,
        permission: "accounting.reports.equity_statement.view",
      },
      {
        type: "link",
        href: "/accounting?tab=general-ledger",
        labelKey: "accounting.tabs.general_ledger",
        icon: FileText,
        permission: "accounting.reports.general_ledger.view",
      },
      {
        type: "link",
        href: "/accounting?tab=vat-summary",
        labelKey: "accounting.tabs.vat_summary",
        icon: Receipt,
        permission: "reporting.vat.view",
      },
      {
        type: "link",
        href: "/accounting?tab=vat-detail",
        labelKey: "accounting.tabs.vat_detail",
        icon: Receipt,
        permission: "reporting.vat.view",
      },
      {
        type: "link",
        href: "/accounting?tab=customer-subledger",
        labelKey: "accounting.tabs.customer_subledger",
        icon: BookUser,
        permission: "payment.subledger.view",
      },
      {
        type: "link",
        href: "/accounting?tab=vendor-subledger",
        labelKey: "accounting.tabs.vendor_subledger",
        icon: Coins,
        permission: "payment.subledger.view",
      },
      {
        type: "link",
        href: "/accounting?tab=ar-aging",
        labelKey: "accounting.tabs.ar_aging",
        icon: Banknote,
        permission: "payment.aging.view",
      },
      {
        type: "link",
        href: "/accounting?tab=ap-aging",
        labelKey: "accounting.tabs.ap_aging",
        icon: ArrowLeftRight,
        permission: "payment.aging.view",
      },
      {
        type: "link",
        href: "/accounting?tab=fiscal-periods",
        labelKey: "accounting.tabs.fiscal_periods",
        icon: Lock,
        permission: "accounting.fiscal_period.manage",
      },
      {
        type: "link",
        href: "/accounting?tab=cost-centers",
        labelKey: "accounting.tabs.cost_centers",
        icon: PieChart,
        permission: "accounting.cost_centers.view",
      },
      {
        type: "link",
        href: "/accounting?tab=cost-center-report",
        labelKey: "accounting.tabs.cost_center_report",
        icon: PieChart,
        permission: "accounting.reports.cost_center.view",
      },
    ],
  },
  {
    type: "group",
    labelKey: "nav.fixed_assets",
    icon: Landmark,
    iconColor: "text-amber-600",
    children: [
      { type: "link", href: "/fixed-assets", labelKey: "accounting.tabs.fixed_assets", icon: Landmark, permission: "fixed_assets.view" },
      { type: "link", href: "/fixed-assets/categories", labelKey: "fixed_assets.categories.title", icon: FolderTree, permission: "fixed_assets.view" },
      {
        type: "link",
        href: "/fixed-assets/depreciation-schedule",
        labelKey: "fixed_assets.schedule.title",
        icon: BarChart3,
        permission: "fixed_assets.view",
      },
      { type: "link", href: "/fixed-assets/card", labelKey: "fixed_assets.card.title", icon: IdCard, permission: "fixed_assets.view" },
      {
        type: "link",
        href: "/fixed-assets/reconciliation",
        labelKey: "fixed_assets.reconciliation.title",
        icon: ClipboardCheck,
        permission: "fixed_assets.view",
      },
    ],
  },
  {
    type: "group",
    labelKey: "nav.inventory",
    icon: Boxes,
    iconColor: "text-cyan-600",
    children: [
      { type: "link", href: "/inventory?tab=warehouses", labelKey: "inventory.tabs.warehouses", icon: Warehouse, permission: "inventory.warehouse.view" },
      { type: "link", href: "/inventory?tab=stock", labelKey: "inventory.tabs.stock", icon: PackageSearch, permission: "inventory.stock.view" },
      { type: "link", href: "/inventory?tab=moves", labelKey: "inventory.tabs.moves", icon: ArrowLeftRight, permission: "inventory.stock.view" },
      { type: "link", href: "/inventory?tab=transfer", labelKey: "inventory.tabs.transfer", icon: Truck, permission: "inventory.transfer.create" },
      {
        type: "link",
        href: "/inventory?tab=cycle-counts",
        labelKey: "inventory.tabs.cycle_counts",
        icon: ClipboardCheck,
        permission: "inventory.stock.view",
      },
      { type: "link", href: "/inventory?tab=cardex", labelKey: "inventory.tabs.cardex", icon: FileText, permission: "inventory.stock.view" },
      { type: "link", href: "/inventory?tab=stock-balance", labelKey: "inventory.tabs.stock_balance", icon: PackageSearch, permission: "inventory.stock.view" },
      { type: "link", href: "/inventory?tab=valuation", labelKey: "inventory.tabs.valuation", icon: Coins, permission: "reporting.inventory_valuation.view" },
      { type: "link", href: "/inventory?tab=inventory-reconciliation", labelKey: "inventory.tabs.reconciliation", icon: Scale, permission: "reporting.inventory_valuation.view" },
      {
        type: "link",
        href: "/inventory?tab=low-stock",
        labelKey: "inventory.tabs.low_stock",
        icon: AlertTriangle,
        permission: "inventory.stock.view",
      },
    ],
  },
  {
    type: "group",
    labelKey: "nav.purchasing",
    icon: Truck,
    iconColor: "text-rose-600",
    children: [
      { type: "link", href: "/purchasing", labelKey: "nav.purchasing.orders_bills", icon: Truck, permission: "purchasing.order.view" },
      { type: "link", href: "/purchasing/returns", labelKey: "nav.purchasing.returns", icon: Undo2, permission: "purchasing.vendor_bill.view" },
      { type: "link", href: "/purchasing/payments", labelKey: "purchasing.payments.title", icon: Banknote, permission: "payment.view" },
      { type: "link", href: "/purchasing/reports", labelKey: "nav.purchasing.reports", icon: BarChart3, permission: "reporting.purchasing.view" },
    ],
  },
  {
    type: "group",
    labelKey: "nav.master_data",
    icon: Package,
    iconColor: "text-fuchsia-600",
    children: [
      { type: "link", href: "/master-data/products", labelKey: "nav.master_data.products", icon: Package, permission: "product.view" },
      { type: "link", href: "/master-data/categories", labelKey: "nav.master_data.categories", icon: FolderTree, permission: "product_category.view" },
      { type: "link", href: "/master-data/uom", labelKey: "nav.master_data.uom", icon: Ruler, permission: "uom.view" },
      { type: "link", href: "/master-data/address-book", labelKey: "nav.master_data.address_book", icon: BookUser, permission: "partner.view" },
      { type: "link", href: "/master-data/customers", labelKey: "nav.master_data.customers", icon: Users, permission: "partner.view" },
      { type: "link", href: "/master-data/vendors", labelKey: "nav.master_data.vendors", icon: Building2, permission: "partner.view" },
      { type: "link", href: "/master-data/employees", labelKey: "nav.master_data.employees", icon: IdCard, permission: "partner.view" },
    ],
  },
  {
    type: "group",
    labelKey: "settings.title",
    icon: Settings,
    iconColor: "text-slate-500",
    children: [
      { type: "link", href: "/settings/company", labelKey: "settings.section.company", icon: Building2, permission: "company.view" },
      { type: "link", href: "/settings/security", labelKey: "settings.section.security", icon: ShieldCheck, permission: "role.manage" },
      { type: "link", href: "/settings/account", labelKey: "settings.section.account", icon: UserCog },
    ],
  },
];
