# 18 — UI/UX System-Wide Audit

**Status:** Audit complete. **No fixes implemented.** This document is a findings report only, delivered per the Owner's explicit instruction: *"ابدأ بالـ Audit فقط، ثم توقف وأرسل التقرير المنظم"* (start with the Audit only, then stop and send the organized report).

**Method:** Live walkthrough of the real running app (frontend on `localhost:3000`, backend on `localhost:8000`) logged in as `demo-general@example.com` ("General Demo Trading Co.", 10 records/master type, 10 transactions/module — built in the prior session), plus direct reading of the actual frontend and backend source for every finding below. No finding in this report is inferred or assumed — each cites the specific file(s)/route(s)/live observation it is based on. Screenshots were not obtainable this session (the browser preview pane could not composite frames), so evidence is the accessibility tree (`read_page`)/page text captured live, plus source reads.

**Severity scale:** Critical / High / Medium / Low / Already Good — as instructed. "Already Good" entries are included because the Owner asked what should explicitly **not** be touched or rebuilt.

---

## Executive Summary

The system is functionally correct and financially trustworthy where it has been recently built (Accounting, Payments) — those two modules should be the *reference standard* the rest of the app is brought up to, not rebuilt. The core problem is not broken screens; it's **two different UI qualities coexisting in the same app**: a well-built shared-component pattern (search, sort, pagination, permission-gating, consistent empty/error states, formatted currency) used in Master Data / Sales-Quotations / Payments / Accounting, versus hand-rolled, inconsistent screens in Purchasing and Inventory that skip nearly all of that. On top of that, one Critical, system-wide gap: **there is no company-selection UI anywhere** — login silently picks whichever company happens to be first in the token, and there is no way to see or switch to a second company even if the user is authorized for one.

Nothing found here requires a new framework, a new library, or an architecture change. Every fix identified is either frontend-only, or frontend work against an API/data field that already exists.

---

## Part A — Cross-Cutting Pattern Findings (fix once, not per screen)

These are the highest-leverage findings: the same defect repeats across multiple screens because two different implementation patterns exist side by side. Per the Owner's standing rule, each is written up **once**, not per screen.

### A1. Two competing list-screen patterns — most transactional screens use the weaker one
- **Screens on the strong pattern** (`ERPListView` — search, column sort, pagination, permission-gated Create button, shared loading/empty/error states, refresh): `/sales/quotations`, `/payments`, `/master-data/products`, `/master-data/uom`. Customers/Vendors use a sibling shared component, `PartnerListView`.
- **Screens on the weak pattern** (hand-rolled `<Table>` inside a `<Tabs>` panel, no search, no sort, no pagination, no permission gating on the Create/Approve buttons, empty state is an inline `{data?.length===0 && <TableRow>…}` instead of the shared `EmptyState`): **`/purchasing`** (both the Orders tab and the Vendor Bills tab) and **`/inventory`** (all four tabs: Warehouses, Stock, Moves, Transfer).
- **Evidence:** read of `frontend/app/(dashboard)/purchasing/page.tsx` (171 lines, `OrdersTab`/`VendorBillsTab`, raw `<Table>`) and `frontend/app/(dashboard)/inventory/page.tsx` (445 lines, four tabs, same pattern), compared against `frontend/app/(dashboard)/sales/quotations/page.tsx` and `frontend/app/(dashboard)/payments/page.tsx`, which both build their columns and pass them to `ERPListView`.
- **Why it matters:** these are the screens an Owner/clerk will live in daily (purchase orders, vendor bills, stock, transfers). Today none of them can be searched or sorted, and once record counts grow past what fits on one screen (the ~100-record Milestone 3 dataset, or real production volume), they become unusable — there is no pagination at all, every row renders in one unbounded table.
- **Proposed solution:** migrate `OrdersTab`, `VendorBillsTab`, and all four Inventory tabs onto `ERPListView`, the same way `sales/quotations/page.tsx` already does it. The list data (`purchasingApi.listOrders`, `.listVendorBills`, `inventoryApi.listWarehouses/listStockQuants/listStockMoves`) already exists and needs no change.
- **Frontend-only.** No architecture change. Achievable without touching the backend at all.
- **Severity: High** (systemic, affects the majority of day-to-day transactional screens).

### A2. No shared currency/number formatting — financial figures render inconsistently
- **Formatted correctly:** Dashboard KPIs (`"5,360.15 SAR"`, thousands separator + fixed 2 decimals + currency code, via a local `formatSar()` helper), Accounting's GL/Income Statement/Balance Sheet, Payments' list/detail.
- **Rendered raw, with no formatting at all:** Sales quotation/order/invoice totals (`{quotation.total_amount}`, `{order.total_amount}`, `{invoice.total_amount}` — the raw string straight from the API, e.g. `"1250.0000"` with 4 raw decimal places and no grouping, no currency suffix), Purchasing order/bill totals (same pattern, `{o.total_amount}` / `{b.total_amount}`), Inventory stock qty/avg-cost/move unit-cost (same).
- **Evidence:** `grep` for `total_amount`/`toLocaleString`/`SAR` across `frontend/app`: only 3 files (`dashboard/page.tsx`, `accounting/page.tsx`, `setup/page.tsx`) do any currency formatting; direct reads of `sales/quotations/[id]/page.tsx:58`, `sales/orders/[id]/page.tsx:54`, `sales/invoices/[id]/page.tsx:70,74`, `purchasing/page.tsx:67,124` confirm raw interpolation.
- **Why it matters:** an ERP's core credibility is trustworthy-looking numbers. A Sales Invoice showing `1250.0000` next to a Dashboard showing `1,250.00 SAR` for the same kind of figure reads as an unfinished product, and raw 4-decimal amounts (the DB's internal `Numeric(18,4)` precision) are not what should ever reach a screen.
- **Proposed solution:** one shared `formatCurrency(amount, currencyCode, locale)` utility (this was already flagged as a gap in `docs/erp-ux-standard.md` before this audit), adopted everywhere money is displayed.
- **Frontend-only.**
- **Severity: High.**

### A3. `FormView` (shared create/edit form shell) used in only 3 of ~9 data-entry screens
- **Used correctly:** `payments/new`, `master-data/partners/new` (Customers/Vendors), `master-data/products/new` — each gets a consistent title/breadcrumbs/Save/Cancel/inline-error/saving-state treatment for free.
- **Not used:** `sales/quotations/new`, `purchasing/orders/new`, and all three Inventory inline forms (Warehouses, Stock receive, Transfer) — each hand-builds its own Card + Button + local error `<p>`, with small but real inconsistencies (e.g. Inventory's "receive stock" button is disabled based on a different condition style than Purchasing's "new order" button).
- **Evidence:** `grep "FormView"` across `frontend/app` → exactly 3 files.
- **Severity: Medium.** Frontend-only.

### A4. Zero schema-level form validation anywhere — `zod` and `react-hook-form` are installed but unused
- **Evidence:** both packages are in `package.json`/`package-lock.json`; `grep 'from "zod"'` / `'from "react-hook-form"'` across the entire frontend → **0 matches**. Every form validates only via native HTML `required` and manual `disabled={!field}` checks (e.g. `master-data/products/new/page.tsx:75`, `saveDisabled={!sku || !name}`) — there is no format validation (a negative quantity, a price of `"abc"`, an invalid email on a partner form) and no per-field inline error message; a bad value is only caught when the backend rejects it and the raw API error string is shown.
- **Why it matters:** this is exactly the kind of mistake real data entry produces (a clerk mistyping a quantity), and today the only feedback is a generic error banner after a failed save, not a field-level warning before it.
- **Proposed solution:** adopt `zod` + `react-hook-form` (already-installed, zero new dependencies) starting with the highest-risk numeric/date fields (quantities, prices, dates) across quotation/order/bill line-item forms.
- **Frontend-only.** **Severity: Medium.**

### A5. `<Can>` permission gate used in only 3 files, all Master Data
- **Evidence:** `grep "<Can[ >]"` across the frontend → `master-data/uom/page.tsx`, `master-data/categories/page.tsx`, and the shared `erp-list-view.tsx` itself (which gates the Create button when a `permission` prop is passed — this is how Sales Quotations and Payments get gating "for free" through `ERPListView`, without their own `<Can>` usage).
- **Not gated:** Purchasing's "Approve Bill" button, Inventory's create-warehouse/receive-stock/transfer buttons, Sales' credit-note button on the Invoice page — all render unconditionally regardless of the logged-in user's actual permissions.
- **Why it matters:** a user without the relevant permission sees a live, clickable button, clicks it, and only then receives a raw backend 403 — this is a worse experience than the button simply not being there, and is made more likely by a real, previously-documented gap: there is no API today to grant a new permission to an already-existing role, so under-permissioned users/roles are common in practice, not a hypothetical.
- **Proposed solution:** wrap these actions in `<Can>`, consistent with how Master Data already does it.
- **Frontend-only.** **Severity: High** (directly caused by clicking a visibly-enabled control and hitting a wall).

### A6. UI states (loading/empty/error) reimplemented ad hoc outside Master Data/Sales-Quotations/Payments/Accounting
- Shared components exist and work well (`components/erp/states/{empty-state,error-state,not-found,permission-denied}.tsx`, `components/ui/skeleton.tsx`) and are used correctly where `ERPListView`/`FormView` are used.
- Purchasing and Inventory instead inline their own empty-row markup (`{data?.length === 0 && <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">{t("common.empty")}</TableCell></TableRow>}`, repeated near-verbatim 5 times across the two files) and their own inline destructive-text error paragraphs.
- **Severity: Low–Medium** (cosmetic/consistency, not broken). Resolved automatically once A1 is fixed (adopting `ERPListView` brings the shared states with it). **Frontend-only.**

### A7. No toast/notification system anywhere in the app
- **Evidence:** `grep "toast|Toast|sonner"` across the frontend → **0 matches**, confirming the gap already flagged (pre-audit) in `docs/erp-ux-standard.md`.
- Every successful mutation (approve a vendor bill, create a payment, post a journal entry, complete a stock transfer) communicates success only by silently refetching the underlying list — there is no confirmation message at all. The user has to notice the table changed.
- **Why it matters:** with 10 demo records this is barely noticeable; it becomes a real problem once lists are long enough that a changed row isn't visibly obvious, or on slower connections where the refetch isn't instant.
- **Proposed solution:** one shared toast primitive, wired into each mutation's `onSuccess`.
- **Frontend-only.** **Severity: Medium.**

---

## Part B — Login / Company Context (audited as one integrated flow, per instruction)

### B1. No company-selection UI exists anywhere — Critical
- **Evidence, read directly:**
  - `frontend/lib/jwt.ts` — `firstAuthorizedCompany(token)` decodes the JWT's `authorized_companies` claim (format `"companyId:branchId"`, one entry per authorized company) and **always returns `authorized_companies[0]`**, with a comment acknowledging this ("no separate 'list my companies' endpoint exists... read for UI convenience only").
  - `frontend/app/(auth)/login/page.tsx:47-51` — `applyTokens()` calls `firstAuthorizedCompany(accessToken)` and immediately `setActiveCompany(...)` then redirects to `/dashboard`. There is no branch in this code for "more than one company" — it behaves identically whether the token has 1 or 5 authorized companies.
  - `grep "setActiveCompany|switchCompany|authorized_companies"` across every `.tsx` file in the frontend → the **only** call site of `setActiveCompany` in the entire app is that one line in `login/page.tsx`. There is no company switcher in the Topbar, no settings page, nothing — once logged in, the active company is fixed for the rest of the session with no way to change it short of logging out (and logging back in reapplies the exact same silent `[0]`-index logic).
- **Why it matters:** this is not a hypothetical — it's the exact scenario the Owner named (a user, e.g. an accountant or the Owner personally, legitimately authorized for more than one company). Today that user cannot ever reach their second company through the UI, cannot even discover it exists, regardless of how many times they log in. This has not surfaced yet only because every real test login built so far (Companies A/B/C, General Demo) is single-company by construction.
- **Proposed solution** (matches the Owner's stated required flow exactly): after a successful login, decode `authorized_companies`. If length is 1, proceed straight to the dashboard (this is correct, desired behavior for the common case, and should stay). If length > 1, show an explicit company-selection screen before entering the dashboard; the chosen company becomes Active and the rest of the session behaves as it does today. A way to reopen that switcher later (without a full logout) is a reasonable companion, but the minimum bar is: no user is ever silently defaulted into a company without a choice when more than one exists.
- **Frontend-only for the picker UI.** The backend already returns everything needed — no new endpoint, no schema change, no architecture change. This is UI wiring on top of an already-existing JWT claim.
- **Severity: Critical** — this is the item the Owner named explicitly as the audit's top priority.

### B2. Company name display is now real, but inconsistent between two places on the same screen — new finding, found live during this audit
- **Live evidence** (General Demo Trading Co., Arabic locale, `/dashboard`, captured via `read_page`): the Topbar shows **"شركة العرض التجريبي العام للتجارة"** (the Arabic legal name) while the Dashboard body, directly under the page title, shows **"General Demo Trading Co."** (the English legal name) — two different names for the same company, on the same screen, in the same locale.
- **Root cause, read directly:** `components/layout/topbar.tsx:37` picks `locale === "ar" ? companyQuery.data?.legal_name_ar : companyQuery.data?.legal_name` (locale-aware), while `app/(dashboard)/dashboard/page.tsx:45` always renders `companyQuery.data.legal_name` (not locale-aware) — these were built in the same recent pass (company-name-visibility work, prior to this audit) but with two different implementations.
- **Why it matters:** small, but directly undermines the very fix it's part of — the whole point of always showing the company name was to remove ambiguity about which company you're in; showing two different names for it on one screen reintroduces exactly that ambiguity.
- **Proposed solution:** make the Dashboard use the same locale-aware selection as the Topbar (ideally both call one shared `useCompanyName()` hook instead of duplicating the ternary).
- **Frontend-only, trivial.** **Severity: Medium.**

---

## Part C — Navigation / Information Architecture

### C1. Sales Orders and Sales Invoices have no list page — only reachable by deep link
- **Evidence:** `frontend/app/(dashboard)/sales/` contains `quotations/page.tsx` (list, real), `quotations/[id]/page.tsx`, `quotations/new/page.tsx`, but only `orders/[id]/page.tsx` (detail — **no `orders/page.tsx`**) and only `invoices/[id]/page.tsx` (detail — **no `invoices/page.tsx`**, and no `invoices/new/page.tsx`). `lib/nav-config.ts` confirms this is intentional and documented ("Deliberately does NOT include every item from the target ERP nav structure... none of those have a real page behind them yet, and fake nav entries with no destination are explicitly prohibited") — a genuinely disciplined choice, not an oversight.
- **Why it matters anyway:** Orders and Invoices are the core sales documents — more central to daily use than Quotations. Today a user can only reach a specific Order or Invoice if they already have its ID (from a quotation-conversion redirect, or a drill-down link from Payments/Accounting). There is no way to browse "all my Sales Orders this month" or "all unpaid Sales Invoices" at all.
- **Severity: Critical for Sales specifically** — this is a bigger practical gap than any purely cosmetic finding in this report, even though each individual page (`orders/[id]`, `invoices/[id]`) is itself well-built.
- **Frontend/Backend split, confirmed by reading `backend/src/modules/sales/api/routes.py`:** a list endpoint for Invoices already exists (`GET /invoices`, line 155) — the Invoice list page is **frontend-only**, same `ERPListView` pattern as `quotations/page.tsx`. Sales Orders is different: the backend has **only** `GET /orders/{order_id}` (single order by id) — **no `GET /orders` list route exists at all**. Building a Sales Orders list page therefore needs a small backend addition first (a list endpoint, following the exact shape of the existing `list_invoices`/`list_quotations` handlers) before the frontend page can be built. This is a genuine, verified Frontend+Backend item, not frontend-only — flagged precisely per the Owner's classification requirement.

### C2. No unified "Reports" destination anywhere
- **Evidence:** `nav-config.ts` has no Reports entry. `features/reporting/api/client.ts` exposes exactly one method, `getDashboard` — the two CSV-export backend endpoints (confirmed to exist on the backend in an earlier phase of this engagement) have **zero** frontend caller and are unreachable from the UI. GL/Income Statement/Balance Sheet/Customer & Vendor Subledgers/AR & AP Aging all live as tabs inside `/accounting`, which works but isn't a discoverable "reports" concept.
- **Why it matters:** the Owner's Standard ERP Report Catalog goal (tracked in `docs/master-execution-plan.md` §D3.3) implies a place a user goes to find "all reports" — today that place doesn't exist, and two already-built report exports are completely invisible.
- **Severity: High** (dead, invisible functionality) for the CSV exports specifically; **Medium** for the broader "no Reports hub" structural point, since the reports that do exist are at least reachable via Accounting.
- **Frontend-only** to wire the CSV buttons; a dedicated Reports hub is a slightly larger frontend-only navigation change, no backend/architecture work.

---

## Part D — Module Notes (concise — most detail already covered in Parts A–C)

- **Sales:** Quotations screen is the best-built screen in the app (the deliberate `ERPListView` reference implementation — see its own code comment). Real gap found live: the Invoice detail page (`sales/invoices/[id]/page.tsx`) shows Type/Subtotal/VAT/Total and the ZATCA QR, but never surfaces which Sales Order it came from — even though `SalesInvoice.sales_order_id` is a real, populated nullable FK in the backend model (`backend/src/modules/sales/infrastructure/models.py:110`). This is a near-free traceability win, the same shape as the JE `source_table` win from Milestone 1b — the data already exists, it's just not exposed. **Medium, frontend-only** (add the field to the API schema if not already present, render it as a link).
- **Purchasing:** functional but carries A1/A2/A5 in full. Vendor Bill still has no detail page at all (documented known limitation from Milestone 1b) — Subledger/GL drill-down to a bill shows a label, not a link.
- **Inventory:** four tabs work, but carry A1/A2/A5/A6 in full, and **Cycle Count has zero UI** despite a complete backend workflow — confirmed live in `backend/src/modules/inventory/api/routes.py`: `POST /cycle-counts` (create) and `POST /cycle-counts/{id}:approve` (which posts a real, balanced journal entry with `source_table="cycle_count_line"`) both exist and are fully wired to accounting, but no page, tab, or link anywhere in the frontend calls either. This is a complete, accounting-correct feature that is entirely invisible to the Owner today. **High, frontend-only** (the backend needs nothing — this is a pure UI-build item, larger than a "fix" and closer to finishing a module). Secondary, smaller finding: the Stock/Transfer product picker is a plain unsearchable `<Select>` listing every product with no filtering — fine at 10 products, becomes unusable once the ~100-record Milestone 3 dataset lands. **Low today, will become Medium.**
- **Payments:** the most mature module in the system — `ERPListView`, `FormView`-style creation, a real invoice/bill picker, a proper detail page, and drill-down links that work. **Already Good** — treat as the reference standard, not a target for rework.
- **Accounting:** recently built out (Milestones 1a/1b) — consistent internal tab pattern, correct print statements (chrome now hidden, company name now shown). **Already Good**, aside from the B2 locale-name inconsistency noted above.
- **Reports:** see C2.
- **Traceability:** the Journal-Entry → source-document drill-down (`lib/source-document-links.ts`) is deliberately and honestly scoped — only `sales_invoice` and `payment` get a real link today; everything else (`vendor_bill`, `goods_receipt`, `cycle_count_line`) shows a label with no link, by explicit design, because no detail page exists yet for those source types. This is good discipline (no broken links), not a bug — it will resolve naturally as C1/D's Vendor Bill and Cycle Count screens get built. The one genuine gap found is the Sales Order↔Invoice link noted above.
- **Arabic/English/RTL:** verified live by toggling locale on the Dashboard — sidebar, topbar, and page content all translate correctly and instantly, `dir` flips as expected, this is real infrastructure, not cosmetic. One good pattern worth reusing more broadly: the Product form's `name_ar` field explicitly forces `dir="rtl"` on its input (`master-data/products/new/page.tsx:89`) — this pattern was not verified as present on the Customer/Vendor partner form in this pass; flagged as an open item to check, not a confirmed finding.
- **UI States / Tables / Forms:** fully covered under Part A (A1, A3, A4, A6).

---

## Part E — Already Good (do not rebuild)

- `ERPListView` + its `FilterBar`/pagination internals — genuinely well-built (search, sort, pagination, permission-gated Create, refresh, consistent empty/error/loading states). The problem is adoption, not the component.
- `FormView` — same: well-built, under-adopted.
- The Payments module, end to end.
- The Accounting module, end to end (GL, Income Statement, Balance Sheet, Customer/Vendor Subledgers, AR/AP Aging, print statements).
- i18n/RTL infrastructure (`useI18n()`, `dir` flipping) — real and functional.
- `<Can>` permission gate + `use-permissions.ts` — correct where used, just under-adopted (A5).
- The Category tree UI (`master-data/categories/page.tsx`) — a genuinely different pattern for a genuinely different (hierarchical) data shape; this is a legitimate exception, not an inconsistency to fix.
- The JE `source_table`/`source_id` traceability mechanism and its honest "label only, no broken link" fallback — good design discipline.

---

## Findings Summary Table

| # | Finding | Area | Severity | Frontend/Backend | Architecture change? |
|---|---|---|---|---|---|
| B1 | No company-selection UI; login silently picks `authorized_companies[0]` | Login/Company Context | **Critical** | Frontend-only | No |
| C1 | No Sales Invoice list page | Navigation / Sales | **Critical** | Frontend-only (`GET /invoices` already exists) | No |
| C1b | No Sales Order list page — and no `GET /orders` list endpoint exists at all | Navigation / Sales | **Critical** | **Frontend + Backend** (small new list endpoint needed) | No |
| A1 | Purchasing/Inventory use a weaker hand-rolled list pattern (no search/sort/pagination/permission-gating) | Cross-cutting | High | Frontend-only | No |
| A2 | No shared currency formatting; Sales/Purchasing/Inventory show raw unformatted amounts | Cross-cutting | High | Frontend-only | No |
| A5 | `<Can>` gate used in only 3 files; unpermitted users see and can click actions they'll be 403'd on | Cross-cutting | High | Frontend-only | No |
| D-Inventory | Cycle Count has a complete backend workflow but zero frontend UI | Inventory | High | Frontend-only | No |
| C2 | 2 CSV export endpoints are completely unreachable from the UI; no unified Reports hub | Reports | High (exports) / Medium (hub) | Frontend-only | No |
| A3 | `FormView` used in only 3 of ~9 forms | Cross-cutting | Medium | Frontend-only | No |
| A4 | Zero schema validation; `zod`/`react-hook-form` installed but unused | Cross-cutting | Medium | Frontend-only | No |
| A7 | No toast/notification system; success is silent everywhere | Cross-cutting | Medium | Frontend-only | No |
| B2 | Company name shown inconsistently (Topbar locale-aware, Dashboard not) | Company Context | Medium | Frontend-only | No |
| D-Sales | Invoice detail doesn't surface its own `sales_order_id`, though the FK exists | Sales / Traceability | Medium | Frontend-only | No |
| A6 | Empty/error states reimplemented ad hoc outside the shared components | Cross-cutting | Low–Medium | Frontend-only | No |
| D-Inventory-2 | Product picker in Stock/Transfer is an unsearchable flat list | Inventory | Low (today) | Frontend-only | No |

Every single finding in this audit is achievable **without any architecture change**. All but one are **frontend-only** or frontend-work-against-an-existing-API — B1's `authorized_companies` claim, C1's `GET /invoices`, D-Inventory's cycle-count API, and D-Sales' `sales_order_id` field all already exist on the backend exactly as needed. The one exception is **C1b**: a Sales Orders list page needs one small new backend list endpoint first (no schema/architecture change — the table and detail endpoint already exist, only a `GET /orders` list route is missing). No new library is required anywhere (the two libraries needed for A4, `zod`/`react-hook-form`, are already installed and unused).

---

## Proposed Fix Bundle (NOT executed — for Owner scope approval)

Grouped in dependency order — each bundle is sized to be its own checkpoint, small enough to verify end-to-end, and ordered so later bundles benefit from earlier ones (e.g., Bundle 2's list migrations get shared empty/error states "for free" once A1 lands).

- **Bundle 1 — Foundations (do first, everything else benefits):** shared `formatCurrency()` utility + adopt everywhere (A2); shared toast primitive + wire into all mutations (A7); fix the Dashboard/Topbar company-name locale inconsistency (B2). Small, low-risk, no dependencies.
- **Bundle 2 — Company Context (Critical, the Owner's named priority):** build the company-selection screen for multi-company logins, gated on `authorized_companies.length > 1`; keep today's direct-entry behavior for the single-company case unchanged.
- **Bundle 3 — List-screen consistency:** migrate Purchasing's two tabs and all four Inventory tabs onto `ERPListView` (A1, brings A6 along for free); wrap the now-exposed actions in `<Can>` (A5).
- **Bundle 4 — Sales/Reports gaps:** build the Sales Invoice list page (C1, frontend-only); add the missing `GET /orders` backend endpoint and build the Sales Order list page on top of it (C1b, frontend+backend); surface the Invoice→Order link (D-Sales); wire the two orphaned CSV export buttons or confirm with the Owner they should be dropped (C2).
- **Bundle 5 — Form consistency:** migrate the remaining forms onto `FormView` (A3); introduce `zod` validation on the highest-risk numeric/date fields (A4).
- **Bundle 6 — Cycle Count UI:** build the missing Inventory Cycle Count screen (create + review lines + approve), mirroring the existing backend workflow 1:1. Larger and more self-contained than the others — reasonable as its own checkpoint.

Recommended relative priority if the Owner wants a subset first: **Bundle 2 (Company Context) and Bundle 1 (Foundations) first** — Bundle 2 because it was named explicitly as the top priority and is self-contained; Bundle 1 because A2/A7 touch nearly every other screen and doing them before Bundle 3 avoids re-touching the same files twice. Bundle 4 and Bundle 6 are the two "real functionality currently invisible" items (Sales Orders/Invoices browsing, Cycle Count) and are recommended next given they represent complete backend work with zero UI today.

This is a proposal, not a decision — awaiting the Owner's approval of scope (all bundles, a subset, or reordered) before any implementation begins.
