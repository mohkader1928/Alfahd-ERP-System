# ERP UX/UI Standard

**Purpose:** one shared rulebook for how every screen in this ERP looks and behaves, so no module invents its own Form/Table/Dialog style. This document is descriptive where a pattern already exists and is proven (Phase 17A/17B/17D), and prescriptive where a pattern is still missing and needs to be built before the next UX pass (Master Execution Plan §E / Milestone 6).

**North star (Owner governance update, 2026-08-02): Minimum clicks + Minimum typing + Maximum clarity.** Every pattern below, and every future addition to this document, is judged against that — not against how many features it adds.

> **Reading this as a non-developer:** each section names an existing shared **component** (a reusable building block, like a Lego brick, used across many screens) so that fixing or improving it in one place fixes it everywhere it's used, instead of having to change every screen one by one.

**Evidence basis:** direct inspection of `frontend/components/erp/`, `frontend/components/ui/`, `frontend/components/layout/`, and every shipped screen (Master Data, Sales, Purchasing, Inventory, Accounting, Payments) as of 2026-08-02.

---

## 1. What already exists (the baseline every new screen must reuse)

| Pattern | Shared component | Status |
|---|---|---|
| List/table screen (search, columns, pagination) | `components/erp/list-view/erp-list-view.tsx` (`ERPListView`) | Standard, used by every module |
| Filter controls above a list | `components/erp/filter-bar/filter-bar.tsx` | Standard |
| Pagination | `components/erp/list-view/pagination-bar.tsx` | Standard |
| Create/Edit form screen | `components/erp/form-view/form-view.tsx` (`FormView`) | Standard — handles Save/Cancel, loading, error banner |
| Report screen shell | `components/erp/report-view/report-view.tsx` | Exists, underused (Reporting module is still mostly flat CSV — Master Execution Plan §D) |
| Record detail / summary card | `components/erp/record-card/record-card.tsx` | Standard |
| Breadcrumbs | `components/erp/breadcrumbs/breadcrumbs.tsx` | Standard |
| Confirmation dialog | `components/erp/states/confirm-dialog.tsx` | Standard |
| Empty / Error / Not-found / Permission-denied states | `components/erp/states/*.tsx` | Standard, all four exist |
| Permission-gated UI | `components/erp/permissions/can.tsx` (`<Can>`) | Standard, but **not consistently applied outside Master Data and Payments** — see §11 |
| Category/tree picker | `components/erp/category-select/category-select.tsx` | Standard for hierarchical data |
| Dashboard tiles | `components/erp/dashboard/*.tsx` | Standard |
| Base primitives (Button, Input, Select, Badge, Card, Dialog, Table, Tabs, Textarea, Skeleton) | `components/ui/*.tsx` | Standard, Base UI-based |
| Sidebar / navigation | `components/layout/sidebar.tsx` + `lib/nav-config.ts` | Standard, single config file drives the whole nav |
| Top bar (company/branch switch, theme, locale) | `components/layout/topbar.tsx` | Standard |
| i18n (Arabic/English, RTL/LTR) | `lib/i18n/en.json`, `lib/i18n/ar.json`, `useI18n()` | Standard, real `dir` flipping verified functional |

**Rule going forward: if a new screen needs a list, a form, a filter bar, a confirmation, an empty state, or a permission check — it reuses the component above. It does not build its own.**

---

## 2. Gaps found (missing shared infrastructure — not yet built anywhere)

These are real, verified gaps (grepped for, not assumed), each with a recommended fix. None of these block Milestone 0; they are the concrete input to the Milestone 6 UX pass in the Master Execution Plan.

1. **No shared currency/date/number formatting utility.** Every screen formats amounts and dates ad hoc — e.g. Payments currently displays raw values like `230.0000` instead of `230.00 SAR` / a localized date format. **Fix:** add `lib/format.ts` with `formatCurrency(amount, currencyCode, locale)`, `formatDate(date, locale)`, `formatNumber(n, locale)`, backed by `Intl.NumberFormat`/`Intl.DateTimeFormat`, and adopt it screen by screen during the Milestone 6 pass.
2. **No toast/notification system.** There is no `Toaster`/toast component anywhere in the codebase — success/error feedback today is limited to inline error banners inside `FormView`. A save action gives no confirming toast. **Fix:** add one shared toast primitive (e.g. Sonner-style) and use it for "Saved", "Deleted", "Payment recorded" style confirmations, without turning every action into an intrusive dialog.
3. **`<Can>` permission gating is inconsistent.** It exists and is used correctly in Master Data and Payments, but several Sales/Purchasing/Inventory action buttons (confirm order, post journal entry, etc.) are not wrapped in it — meaning a user without the permission may see a button that then fails server-side instead of being hidden or disabled client-side. **Fix:** audit every workflow action button module-by-module during Milestone 6 and wrap with `<Can>`.
4. **No "saved views" / persisted filter state.** `FilterBar` works per-session but nothing persists a user's preferred filter/sort across visits. Left as a genuine "not required for Business Core" item — noted for later, not scheduled.
5. **No cancel/void action pattern.** Several documents have a `cancelled` status value in the data model with no UI (or API) path to reach it (Master Execution Plan §D). When this is built, it must use the existing `ConfirmDialog` pattern, not a new one.

---

## 3. Navigation & information architecture

- **Sidebar** (`components/layout/sidebar.tsx`) is driven entirely by `lib/nav-config.ts` — a single ordered list of `{ type: "link", href, labelKey, icon }` entries (plus section groupings for Master Data). Any new module adds one entry here; no sidebar code changes.
- **Breadcrumbs** appear on every list and form screen via the shared `Breadcrumbs` component, always ending in the current screen's own label — this is what lets a user go "Payments → New Payment" back to "Payments" in one click.
- **Page headers**: title + optional primary action (e.g. "New Payment") top-right, consistent across all modules via `ERPListView`'s built-in header slot — a new screen should not hand-roll its own header row.

## 4. Forms

- Built on `FormView`: title, breadcrumbs, `onSave`/`onCancel`, `isSaving`, `saveDisabled`, and a single `error` slot rendered as a banner.
- Field layout: a responsive 2-column grid (`grid-cols-1 sm:grid-cols-2`) is the established pattern (see Payments' `new/page.tsx`); full-width fields use `sm:col-span-2`.
- Selects always use Base UI's `Select`/`SelectTrigger`/`SelectContent`/`SelectItem`, and **must** pass a resolver function to `SelectValue` when the stored value is an ID (`{(v) => list?.find(x => x.id === v)?.name ?? v}`) — omitting this shows a raw UUID to the user, a real bug found and fixed once already in Payments (§10 below codifies this so it isn't rediscovered per-module).
- Dependent selects (a document picker that only loads after a partner is chosen) use TanStack Query's `enabled: !!parentValue` — the pattern Payments established; new multi-step pickers should copy it rather than inventing a new one.
- Derived/default values (e.g. "default the amount to the outstanding balance, but let the user override it") use the *derived-state* pattern — a nullable override state combined with `override ?? computedDefault` at render — **not** a `useEffect` that calls `setState`, which trips the project's `react-hooks/set-state-in-effect` lint rule and causes extra renders.

## 5. Tables / Lists

- `ERPListView` owns: search box, column visibility, sorting, `PaginationBar`, row actions, and the empty/loading/error states — a new list screen configures columns and a query, it does not rebuild the shell.
- Numeric/currency columns use `font-variant-numeric: tabular-nums` (via the shared table styles) so figures align — verify this holds once `lib/format.ts` (§2.1) lands.
- Status is always shown as a `Badge` (`components/ui/badge.tsx`), never as raw text — this is already consistent across Sales, Purchasing, Payments.

## 6. Filters, search, sorting, pagination

- `FilterBar` sits directly above `ERPListView`'s table; filters are simple controls (select/date range/text) that update query params consumed by the list's data query — this is the pattern to extend when the real Reporting screens (Master Execution Plan Milestone 2) are built, rather than each report inventing its own filter UI.
- Pagination is always server-driven through `PaginationBar`, never a client-side slice of a full result set.

## 7. Empty / loading / error / not-found / permission-denied states

All five exist as shared components today (`components/erp/states/*.tsx`) and every list screen already uses the empty/error/loading trio. **Rule:** a new screen never writes its own "No records found" text or spinner — it renders `<EmptyState>` / `<ErrorState>` / a `Skeleton`.

## 8. Confirmations & destructive actions

`ConfirmDialog` is the one and only confirmation pattern — used for delete/deactivate actions in Master Data today. **Rule for anything added later (e.g. the future cancel/void action, §2.5):** reuse `ConfirmDialog`; do not add a second confirmation mechanism, and do not add a confirmation for non-destructive actions (matches the Owner directive's "avoid excessive dialogs" instruction).

## 9. Notifications

Not yet built (§2.2) — this is the one piece of core UX infrastructure genuinely missing. Scheduled as an early Milestone 6 task since several other patterns (save confirmations) depend on it.

## 10. Selects showing IDs instead of labels — a standing rule, not a one-off fix

This exact bug (a Base UI `Select` showing a raw UUID because `SelectValue` had no resolver function) was found and fixed once, live, in Payments. It is codified here specifically so it is checked for, not re-discovered, in every future screen: **any `Select` whose `value` is a database ID must pass a `children` resolver to `SelectValue`.**

## 11. Permission-aware UI

`<Can permission="...">` exists and correctly gates the New Customer/Vendor/Product buttons and the Payments "Create" button. It is not yet applied to several Sales/Purchasing workflow actions (§2.3) — tracked as a Milestone 6 item, not a Business Core blocker, since the API-side permission check already prevents the action from actually succeeding either way (defense in depth, not a security hole).

## 12. Document lifecycle & related documents

Status progression (Draft → Confirmed → Delivered/Invoiced → Paid, etc.) is currently shown only as a `Badge` on the document itself; there is no "related documents" panel (e.g. "this Invoice came from this Sales Order, has these Payments"). This is the natural next step once Customer/Vendor Statements ship (Master Execution Plan Milestone 1/4) and is deferred until those exist, since a related-documents panel is most useful once statements make the relationships visible in one place first.

## 13. Arabic RTL / English LTR

Already real, not cosmetic — verified functional (the whole layout mirrors, not just text alignment) via `dir="rtl"`/`dir="ltr"` driven off the active locale. New screens get this for free as long as they use the shared components above and don't hardcode `left`/`right` (use logical CSS properties or the existing utility classes instead).

## 14. Responsive behavior

`ERPListView`/`FormView` already collapse to a single column below `sm:`. New screens should default to the same `grid-cols-1 sm:grid-cols-2` (or `sm:grid-cols-3` for denser forms) pattern rather than a bespoke breakpoint scheme.

## 15. Keyboard-friendly data entry

Base UI's `Select` supports keyboard navigation natively; during live verification of the Payments picker, keyboard-only selection was found to be less reliable than a direct click in some cases (a testing-tool-level observation, not a confirmed product bug) — worth a deliberate keyboard-navigation pass once Notifications (§9) and the formatting utility (§2.1) are in, rather than chasing it in isolation now.

## 16. Buttons & actions

Primary action = filled `Button` top-right of a list/form header ("New Payment", "Save payment"). Secondary/cancel = outline/ghost variant. This is consistent today; the only rule being added is: **a workflow action that changes document state (Confirm, Post, Approve) must be wrapped in `<Can>`** (§11) going forward.

---

## 17. Company identity — always visible (Owner governance update, 2026-08-02)

The user must never have to wonder "which company am I working in right now?" The active company's name must appear in: the header/topbar (already partially true via the company switcher — needs a gap-check, not a redesign), the Dashboard, every document screen (invoices, bills, payments, journal entries...), every report screen, and — critically — **print/export output and any generated PDF**, where the company name belongs in the document header the same way a real paper letterhead would show it. This is a gap-check against existing screens, using existing components, not a new pattern — tracked as UX Roadmap item 5 (Master Execution Plan §E).

A related, larger question — a single desktop entry point (Login → Owner user → company picker → into that company) — is **not** a UX-pattern decision; it is an open architecture question (browser shortcut vs. installable PWA vs. a packaged native wrapper) recorded for an explicit Owner/Consultant decision in `docs/master-execution-plan.md` §D3.4, not assumed or started here.

## 18. Traceability / drill-down — a required property, not a nice-to-have (Owner governance update, 2026-08-02)

**Every number or document reference on screen must be traceable to its source when that's logically possible.** This was already an informal pattern (§10 above, and Payments' invoice picker) — it is now a required, checked property of every future Milestone's Definition of Done, per `docs/master-execution-plan.md` §D3.1.

**Proven today**: Payments' document picker resolves real names, not IDs (Phase 17D). General Ledger's Reference column opens the real Journal Entry it came from (Milestone 1a, live-verified in a real browser session).

**Not yet built** (tracked, not hidden): Sales Order ↔ Invoice, Purchase Order ↔ Vendor Bill, and Inventory movements back to the document that created them. Each future Milestone that touches these documents must close its own piece of this rather than leaving it for a separate "traceability project" — e.g. Milestone 1b's Customer/Vendor Subledgers must link every line to its real source document as a condition of being considered done, not an enhancement added later.

**Full chain this is building toward**: `Transaction → Source Document → Accounting → Subledger → Report`, navigable in both directions (e.g. a Sales Invoice → its Payment → the Customer Statement it appears on → that customer's Subledger → the General Ledger → the Journal Entry — and back the other way, General Ledger → Journal Entry → the original Invoice).

## How this document is used

- **New screens**: build against §1 only. Do not introduce a new pattern without adding it here first.
- **The Milestone 6 UX pass** (Master Execution Plan §E / Timeline) works directly off §2's gap list, in the order listed (formatting utility and notifications first, since other fixes depend on them; permission-gating audit next; saved views and related-documents panel last, as genuine nice-to-haves).
- This document is updated whenever a new shared pattern is introduced — it must never fall out of sync with what `components/erp/` actually contains.
