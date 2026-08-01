# Phase 17A — ERP Standard UX/UI & Reporting Foundation

Status legend used throughout: **IMPLEMENTED** (built and verified this
phase) · **DESIGNED** (contract/shape exists, not yet consumed by a real
screen) · **DEFERRED** (explicitly out of scope for this phase, listed so
it isn't silently forgotten).

---

## 1. Existing UI architecture (as found, before this phase)

- Next.js 16 App Router, `(auth)` and `(dashboard)` route groups, one
  shared `(dashboard)/layout.tsx` rendering `Sidebar` + `Topbar` + `main`.
- `Sidebar` was a hardcoded flat array of 6 items (`sidebar.tsx`), no
  grouping, no config layer.
- Three pages (Accounting, Inventory, Purchasing) hand-rolled near-identical
  tab+table+filter-row layouts, each with its own copy of the documented
  Base UI `Tabs.Panel` visibility workaround.
- Zero shared list/table component — every list page built its own
  `<Table>` usage directly against `components/ui/table.tsx` primitives.
- Zero breadcrumbs, zero global search, zero permission-aware UI (Create/
  Edit buttons rendered unconditionally regardless of caller's actual
  grants).
- RTL/LTR: already correctly implemented via `I18nProvider` flipping
  `document.dir` and consistent use of logical CSS properties (`text-end`,
  `border-e`, `ps-`/`pe-`) — this was sound and preserved as-is.
- No pagination anywhere: every `list_by_company()` backend endpoint
  returns a bare `list[XOut]` (`limit=200`–`500`), no query params, no
  envelope.
- No endpoint exposed the current user's permissions to the frontend at
  all — `TokenResponse` carries only tokens; `AuthContext` has no
  permissions field.

## 2. Problems discovered

1. `ProductCategory`/pagination/permissions gaps already documented in
   the Phase 17 blueprint — the specific *foundation*-relevant ones this
   phase addresses: no shared list/report/form/card patterns, no
   permission-aware UI plumbing, no hierarchical nav architecture.
2. The "Administration" section of the target nav (Companies/Branches/
   Users/Roles/Audit Log/Settings) has **zero** real pages behind it.
3. The existing `/admin` page is actually "Master Data" (Partners +
   Products) content wearing an "Administration" label — a naming
   mismatch, left as-is this phase (see §15, deferred).

## 3. New shared UI architecture

New `frontend/components/erp/` library:

```
components/erp/
  list-view/erp-list-view.tsx, pagination-bar.tsx
  filter-bar/filter-bar.tsx
  report-view/report-view.tsx
  form-view/form-view.tsx
  record-card/record-card.tsx
  breadcrumbs/breadcrumbs.tsx
  permissions/can.tsx
  states/{empty-state,error-state,permission-denied,not-found,confirm-dialog}.tsx
  dashboard/{dashboard-grid,kpi-card}.tsx
hooks/use-permissions.ts
lib/nav-config.ts
```

All new components are built on the project's existing shadcn/Base UI
primitives (`Card`, `Table`, `Button`, `Select`, `DropdownMenu`, `Dialog`)
— no new UI dependency was added.

## 4. List View standard — IMPLEMENTED

`ERPListView<T>` (`components/erp/list-view/erp-list-view.tsx`): title,
breadcrumbs, search, a `filters` slot (composed with `FilterBar`), sort
(click column header), client-side pagination with page-size selector,
column-visibility toggle, row selection + bulk-action area, permission-
gated Create/Export buttons (via `<Can>`), refresh, and loading/error/
empty states. Search/sort/pagination run **client-side** over the rows
the caller already fetched — no backend list endpoint supports
server-side paging yet (see §9), and at current data volumes (≤500-row
`limit`s) that's the right tradeoff for this phase.

## 5. Filter standard — IMPLEMENTED (component) / DESIGNED (full field set)

`FilterBar` (`components/erp/filter-bar/filter-bar.tsx`) takes a
`FilterFieldConfig[]` (text/select/date), renders active-filter badges
with per-filter clear, and an Apply/Reset pair. The full field vocabulary
from the brief (customer/vendor/product/category/warehouse/location/
account/branch/document type) is supported by the config shape but not
exercised yet — no current screen needs more than 0 filters, since the
one migrated reference page (Quotations) doesn't have filterable
dimensions worth adding before real filter data (categories, statuses
beyond one) exists.

## 6. Form standard — IMPLEMENTED (shell only)

`FormView` (`components/erp/form-view/form-view.tsx`): breadcrumb/title/
status-badge/actions header, a body slot for caller-supplied sections,
and a Save/Cancel footer with error display. Not yet adopted by any
existing form (Quotation/Journal Entry/Purchase Order creation forms) —
per the brief, "establish the reusable architecture... do not redesign
business forms unnecessarily in this phase."

## 7. Record Card standard — IMPLEMENTED (shell only)

`RecordCard` (`components/erp/record-card/record-card.tsx`): header
(name/code/status/actions), summary KPI strip, tabs. Tab visibility uses
the same manual `tab === key && content` gating as every other tabbed
page in this codebase (Base UI's `Tabs.Panel` doesn't reliably hide
inactive panels — see the existing documented workaround in Accounting/
Inventory/Purchasing pages). Not yet consumed — Product/Customer/Vendor/
Account cards don't exist yet (Phase 17E/17F work); this is the shell
they'll be built on.

## 8. Report standard — IMPLEMENTED (shell only)

`ReportView` (`components/erp/report-view/report-view.tsx`): header
(breadcrumb/title/description/filter area/Apply/Reset/Export/Print),
optional KPI summary strip, body (caller's table/grouping/totals as
children), footer. `print:hidden` utility classes hide filter chrome on
print. Not yet consumed — no report endpoints exist yet beyond Trial
Balance (which stays on its current bespoke tab implementation this
phase, per "don't redesign existing business forms/reports").

## 9. Export architecture — DESIGNED

CSV remains the only implemented export mechanism (unchanged, via the
existing `rows_to_csv` backend helper). `ERPListView`'s `exportAction`
and `ReportView`'s `onExport` are wired as caller-supplied callbacks, so
a future CSV/Excel/PDF export can plug in without changing either
component's contract. No Excel/PDF dependency was added — none existed
before this phase and the brief explicitly says not to add one just for
this phase.

## 10. Navigation architecture — IMPLEMENTED

`lib/nav-config.ts` defines `NavLink`/`NavGroup`/`NavEntry`; `Sidebar`
renders it generically with a collapsible chevron for groups. Every
`href` in the config resolves to a real, already-shipped page — no fake
nav entries. Concretely: Dashboard (link), **Sales** (group → Quotations),
Accounting, Inventory, Purchasing, Administration/admin (links, unchanged
from before). The target structure's remaining items (Sales Orders,
Invoices, Customers, Sales Reports, General Ledger, Product Categories,
a true "Administration" group for Companies/Users/Roles/Audit Log...)
have no backing page yet — appending them to `nav-config.ts` is a
one-line change once each page exists in a later phase.

## 11. RTL/LTR rules — IMPLEMENTED, verified live

All new components use only logical CSS properties (`ps-`/`pe-`,
`text-end`, `border-e`, `start-`/`end-`), matching the pre-existing
convention. `Breadcrumbs` and `PaginationBar` explicitly swap their
chevron icon direction based on `useI18n().dir` rather than assuming LTR.
Verified live in the browser: toggling to Arabic mirrors the sidebar to
the trailing edge, right-aligns breadcrumbs/table headers, and both the
sidebar nav and the migrated Quotations page render fully-translated
Arabic strings (breadcrumb, title, search placeholder, column headers,
empty-state text) with no leftover English or layout breakage.

## 12. Permission-aware UI rules — IMPLEMENTED

New endpoint `GET /identity/me/permissions` (self-scoped, any
authenticated caller, backed by the existing
`RoleRepository.get_user_permission_codes()`) → `useMyPermissions()` →
`<Can permission="...">` gates UI-only. `ERPListView`'s `createAction`/
`exportAction` accept an optional `permission` and wrap themselves in
`<Can>` automatically. **This is UX only** — every mutating backend
endpoint still enforces its own `require_permission()` regardless of
what this hook reports; a stale or absent permissions cache can only
ever hide an action the user was already forbidden from completing.

## 13. Component inventory

| Component | Path | Status |
|---|---|---|
| ERPListView | `components/erp/list-view/erp-list-view.tsx` | Implemented, live on Quotations |
| PaginationBar | `components/erp/list-view/pagination-bar.tsx` | Implemented, live |
| FilterBar | `components/erp/filter-bar/filter-bar.tsx` | Implemented, not yet consumed |
| ReportView | `components/erp/report-view/report-view.tsx` | Implemented shell, not yet consumed |
| FormView | `components/erp/form-view/form-view.tsx` | Implemented shell, not yet consumed |
| RecordCard | `components/erp/record-card/record-card.tsx` | Implemented shell, not yet consumed |
| Breadcrumbs | `components/erp/breadcrumbs/breadcrumbs.tsx` | Implemented, live |
| Can | `components/erp/permissions/can.tsx` | Implemented, live |
| EmptyState / ErrorState / PermissionDenied / NotFoundState | `components/erp/states/*` | Implemented; Empty live, others built not yet exercised |
| ConfirmDialog | `components/erp/states/confirm-dialog.tsx` | Implemented, not yet consumed (no destructive action wired to it yet) |
| DashboardGrid / KpiCard | `components/erp/dashboard/*` | Implemented, live on Dashboard |
| useMyPermissions | `hooks/use-permissions.ts` | Implemented, live |
| nav-config | `lib/nav-config.ts` | Implemented, live |

Backend-side (unused-but-ready, per the approved plan):
`src/shared/api/pagination.py` (`PageParams`/`Page[T]`),
`src/shared/reporting/filters.py` (`ReportFilter`) — not consumed by any
existing endpoint; ready for Phase 17B+ reports to build on.

## 14. Future report/list integration pattern

A future report or list endpoint should: define its query params as (or
alongside) `ReportFilter`, return either a bare list (small, bounded
data — matches today's convention) or a future `Page[T]` (once genuine
pagination is needed), and its page should compose `ReportView` or
`ERPListView` with `FilterBar` for its filter chrome rather than
hand-building a new filter row. The Quotations page
(`app/(dashboard)/sales/quotations/page.tsx`) is the reference to copy.

## 15. Explicitly NOT implemented in Phase 17A

- Any new business page (Sales Orders list, Invoices list, Customer/
  Vendor/Product/Account cards, General Ledger, aging, P&L, Balance
  Sheet, any analysis report) — all Phase 17B+.
- Migrating Accounting/Inventory/Purchasing/Admin off their existing
  bespoke tab+table implementations onto `ERPListView` — only Quotations
  was migrated, as the proof-of-pattern reference; the rest migrate
  incrementally as each is touched in a later phase.
- A true "Administration" nav group (Companies/Users/Roles/Audit Log/
  Settings) — no backing pages exist yet.
- Renaming `/admin`'s "Administration" label to "Master Data" — left
  as-is to avoid a presentation change outside this phase's touched-file
  list; worth revisiting when Phase 17B splits Master Data out for real.
- Global search — no component was built; only documented here as
  future scope (search across Customers/Vendors/Products/Sales Orders/
  Invoices/Purchase Orders/Vendor Bills/Journal Entries/Accounts once
  those have list endpoints worth searching).
- Charts on the dashboard — no charting library is installed; adding one
  needs its own decision, not bundled into this foundation phase.
- Server-side pagination on any existing list endpoint — `Page`/
  `PageParams` exist but are not wired into any route; today's `limit`-
  bounded bare-array responses are unchanged.
- Excel/PDF export — CSV only, as before.
- Any change to accounting/inventory/sales/purchasing/payment business
  logic, ZATCA, RLS, tenant isolation, idempotency, or concurrency
  controls.
