# Phase 17 — ERP Standardization: Functional Gap Analysis & Master Blueprint

**Status: design document only. No application code, schema, migration, or
frontend file was modified to produce this document.** Every claim below
was verified by reading the actual repository — route files, model files,
schema files, and frontend page files — not inferred from module names or
assumed from earlier phases' summaries.

---

## 1. Executive Summary

The nucleus is a **real, working transactional backbone** — not a demo.
Six modules genuinely post real accounting entries, deduct real stock,
and generate real ZATCA-chained invoices, all under enforced multi-tenant
isolation (Phase 16A) and with two real concurrency bugs already closed
(Phase 16B). That part of the foundation is sound and does not need
rebuilding.

What it is **not** yet is a *standardized ERP a business can actually run
on day to day*. Nearly everything that makes Odoo (or any comparable
system) feel like an ERP rather than a set of transaction-entry forms is
missing: there is no product classification system exposed anywhere
(the database column exists; nothing can set it), no customer or vendor
"card" with a balance and history, no General Ledger, no aging report, no
P&L or Balance Sheet, no analysis reports of any kind, and the UI has
exactly one flat, six-item sidebar with no search, filters, or export
beyond two CSV downloads. A real electrical/lighting trading company
could technically post transactions in this system today, but could not
answer "how much does this customer owe me," "what's my stock of LED
panels across warehouses," or "show me last quarter's P&L" without a
direct database query.

This is the honest gap this document maps, prioritizes, and sequences —
deliberately not by re-listing what Phase 11/12 already built, but by
tracing what a real user needs *around* those transactions to run a
business.

---

## 2. Current System Baseline

Verified this session, not carried over from memory:

- **Backend**: 37 API endpoints across 6 modules (Identity, Accounting,
  Sales+ZATCA, Inventory, Purchasing, Reporting) — full inventory in §3.
- **Frontend**: 18 page files, one flat sidebar with 6 links, no
  submenus, no breadcrumbs, no global search, no notifications.
- **Tests**: 9 files, 74 tests total (43 milestone smoke tests + 17
  multi-tenancy isolation tests + 7 invoice-duplication tests + 7 others),
  all passing.
- **Docs**: 14 phase documents (`01`–`11`, `14`, `16`, `16b`) — no `12`,
  `13`, `15` as separate files (frontend/testing/documentation phases
  used READMEs instead, per that era's decision).
- **Git history**: 6 commits — initial nucleus, RLS hardening, CORS fix,
  concurrency design, invoice-duplication fix, and this document.

---

## 3. Repository Inventory

### Backend API surface (verified via direct route inspection)

| Module | Endpoints | Notes |
|---|---|---|
| Identity | `bootstrap`, `login`, `verify-2fa`, `GET/POST companies/{id}`, `POST branches`, `GET branches`, `POST users`, `POST users/{id}/roles`, `GET/POST partners`, `GET/POST products`, `GET audit-log` | **No** `GET /users`, **no** role CRUD beyond assignment, **no** `ProductCategory` endpoint of any kind |
| Accounting | `GET/POST chart-of-accounts`, `GET/POST journal-entries`, `POST :post`, `POST :reverse`, `GET reports/trial-balance`, `POST/POST:close fiscal-periods` | Only report is trial balance |
| Sales | `GET/POST quotations`, `POST :confirm`, `GET orders/{id}`, `POST orders/{id}:invoice`, `POST invoices/{id}:credit-note`, `GET invoices/{id}`, `GET quotations/{id}` | No sales-order list endpoint (only get-by-id) |
| Purchasing | `GET/POST orders`, `POST :confirm`, `GET orders/{id}`, `POST goods-receipts`, `POST vendor-bills`, `POST vendor-bills/{id}:approve`, `GET vendor-bills` | No RFQ concept anywhere |
| Inventory | `GET/POST warehouses`, `GET warehouses/{id}/locations`, `POST stock/receive`, `GET stock/quants`, `GET stock/moves`, `POST transfers`, `POST/POST:approve cycle-counts` | No adjustment reason codes, no reorder rules |
| Reporting | `GET dashboard`, `GET export/sales-invoices` (CSV), `GET export/audit-log` (CSV) | Entire reporting surface — 3 endpoints |

### Frontend page inventory (verified via file listing)

```
(auth): login, setup
(dashboard): dashboard, admin (flat Partner+Product CRUD)
  sales: quotations (list), quotations/new, quotations/[id], orders/[id], invoices/[id]
  accounting: page (tabs: CoA / Journal Entries / Trial Balance), journal-entries/[id]
  inventory: page (tabs: Warehouses / Stock / Moves / Transfer)
  purchasing: page (tabs: Orders / Vendor Bills), orders/new, orders/[id]
```
No customer/vendor/product detail ("card") page exists anywhere. No
General Ledger, statement, aging, P&L, or Balance Sheet page exists. No
settings/roles/users management page exists — `admin/page.tsx` only
manages Partners and Products.

### Master data — exact model fields vs. what's exposed (the most
important finding in this inventory)

**`Product`** (`identity/infrastructure/master_data_models.py`) — model
has: `sku`, `name`, `name_ar`, **`category_id`** (FK to `ProductCategory`),
`is_stockable`, `sales_price`, `cost_price`, `default_tax_rate_id`.
`ProductCreateRequest`/`ProductOut` expose: `sku`, `name`, `name_ar`,
`is_stockable`, `sales_price`, `default_tax_rate_id` — **`category_id` and
`cost_price` are on the model but not reachable through the API at all.**
No barcode, brand, model, unit of measure, minimum stock, maximum stock,
or reorder level field exists anywhere in the model — these would need
new columns, not just new API exposure.

**`ProductCategory`** — the table exists (`id`, `company_id`, `name`,
`parent_id` for hierarchy) with **zero API routes**. This is the clearest
possible example of the task's "PLACEHOLDER" category: a real table, a
real FK relationship from `Product`, and no way for any user to ever
create or assign one.

**`Partner`** — model has `name`, `name_ar`, `is_customer`, `is_vendor`,
`vat_number`, `cr_number`, `address` (JSONB). Exposed via API: `name`,
`name_ar`, `is_customer`, `is_vendor`, `vat_number`, `cr_number` — the
`address` JSONB field is on the model but not exposed. **No credit limit,
payment terms, contact phone/email, or partner category field exists on
the model at all.**

**`Role`**/**`Permission`** — fully enforced at the database/RLS and
API-dependency level (confirmed extensively in Phase 16A/16B), but the
only role that ever gets created is the bootstrap-time admin role granted
every permission. There is no endpoint to create a new role, list
existing roles, or assign specific permissions to one.

---

## 4. ERP Functional Benchmark

Structured findings against the requested benchmark areas — condensed
here; the exhaustive per-item table is §17 (Master Gap Matrix).

**Inventory**: on-hand/available quantity, receipts, transfers, FIFO,
average cost, and cycle counts are real and working. Reserved quantity,
incoming/outgoing quantity as distinct concepts, reordering rules,
low-stock alerts, and negative-stock *reporting* (the block exists;
there's no report of *when* it happened) do not exist.

**Accounting**: journals, posting, and trial balance are real. General
Ledger, any statement, any aging, P&L, and Balance Sheet do not exist —
this is the single largest functional hole in the whole system, because
without them, "trial balance" is the *only* financial report a real
bookkeeper can pull.

**Sales**: the whole quotation→order→invoice→credit-note chain works,
including ZATCA. Every analysis report (by customer, product, category,
salesperson, period) and every customer-facing report (statement,
outstanding invoices, balance) is missing.

**Purchasing**: PO→receipt→bill→3-way-match works. RFQ doesn't exist (a
real gap, but explicitly one this nucleus's docs already deferred).
Vendor-side reporting is exactly as absent as sales-side.

**Identity/Master Data**: multi-tenancy and RBAC *enforcement* are
genuinely strong (stronger than most demo ERPs, per the Phase 16 work).
Master data *management* (categories, UOM, roles, users, payment terms)
has almost no UI surface.

---

## 5. UI/UX Standardization

**What exists**: a working, translated (AR/EN), RTL/LTR-aware shell with
a consistent card/table/badge visual language (shadcn on Base UI),
dark/light theming, and RFC 7807 error surfacing threaded through every
API call.

**What's missing, and genuinely missing across *every* module, not
per-screen**:
- **Navigation**: flat 6-item sidebar, no submenus, no breadcrumbs, no
  global search, no notifications.
- **List views**: no consistent search/filter, no group-by, no saved
  filters, no column selection, no bulk actions, no per-row action menu
  beyond a link to detail. Every module built its own bespoke table by
  hand — there is no shared list-view component.
- **Form views**: no consistent header-action pattern (Save/Cancel exist
  per-page but differently), no tabs/sections convention, no
  attachments, no activity/audit trail visible from a record's own page
  (the audit log exists but only as a raw CSV export, not attached to
  the record it's about).
- **Dashboard**: one page, four static KPI cards, no charts, no
  date-range picker, no drill-down from a KPI to its underlying records.
- **Reports**: two CSV exports, no shared filter bar, no print, no
  on-screen preview.

This absence of shared patterns is itself the top UI/UX priority — every
module built its own version of the same list/form/report primitives,
which is exactly the "randomly built screens" outcome this phase exists
to prevent from continuing.

---

## 6. Master Data Standardization

The concrete, evidenced gap: `ProductCategory` exists as a table with
parent/child hierarchy support and zero way to use it. Before any new
product-classification UI is built, the **schema itself needs three
things it doesn't have**: a Unit of Measure concept (no UOM table exists
at all — not even a single flat one), a barcode field, and
min/max/reorder-level fields on `Product`. These are schema changes, not
just new screens — flagged explicitly so Phase 17B (see roadmap) is
scoped correctly as "master data + schema," not "master data UI only."

The electrical/lighting category tree in the original prompt
(`Electrical > Lighting > LED Panels...`) is confirmed to be exactly what
`ProductCategory.parent_id` already supports structurally — the gap is
purely that nothing lets a user create these rows or assign a product to
one.

---

## 7. Inventory Gap Analysis

| Feature | State | Evidence |
|---|---|---|
| Warehouses, locations, receive, transfer | EXISTING AND WORKING | `inventory/api/routes.py`, verified in Phase 12 live browser testing |
| FIFO / average valuation | EXISTING AND WORKING | `inventory/domain/valuation/`, tested |
| Cycle count + adjustment posting | EXISTING AND WORKING | `POST /cycle-counts:approve`, posts a real journal entry |
| Multi-location hierarchy | PARTIAL | `Location.parent_id` exists on the model; only ever one flat "default location" per warehouse is created (`WarehouseService.create_warehouse_with_default_location`) — no UI/API ever creates a second, nested location |
| Stock card (single-product ledger) | MISSING | `GET /stock/moves` returns the whole company's moves, unfiltered by product — no per-product drill-down view |
| Inventory valuation report | MISSING | quant-level moving-average cost exists per row; no aggregate valuation report |
| Reorder rules / low-stock alerts | MISSING | no min/max/reorder fields exist on `Product` at all |
| Negative-stock report | MISSING | the *block* is enforced (`InsufficientStockError`); no report of near-misses or historical negative-stock attempts |
| Inventory by category | MISSING | depends on `ProductCategory` being usable first (§6) |

---

## 8. Accounting Gap Analysis

| Feature | State | Evidence |
|---|---|---|
| Chart of accounts, journals, posting, reversal | EXISTING AND WORKING | `accounting/api/routes.py`, immutability trigger verified in Phase 16A |
| Trial balance | EXISTING AND WORKING | `GET /reports/trial-balance` |
| Fiscal periods | PARTIAL | API exists (`create`/`close`); no frontend page at all |
| General Ledger | MISSING | no endpoint returns per-account transaction detail — trial balance is aggregate-only |
| Customer / Vendor statement | MISSING | no endpoint joins `partner` to `sales_invoice`/`vendor_bill` payment history |
| AR / AP aging | MISSING | no due-date concept exists on `sales_invoice`/`vendor_bill` at all — this is a **schema gap**, not just a report gap |
| P&L / Balance Sheet | MISSING | would need to be built from `account_type` + trial-balance-style aggregation; no endpoint exists |
| Cost centers | PLACEHOLDER | `cost_center` table exists (referenced in `journal_entry_line.cost_center_id`), zero API/UI |
| Tax report | MISSING | `tax_rate`/`tax_group` tables exist and are used for calculation; no report aggregates tax collected/paid |

---

## 9. Sales Gap Analysis

| Feature | State | Evidence |
|---|---|---|
| Quotation → Order → Invoice → Credit Note | EXISTING AND WORKING | Full chain verified live in Phase 12/16B |
| Customer card / 360 view | MISSING | `admin/page.tsx` is a flat create+list, no detail page |
| Customer statement, balance, outstanding invoices | MISSING | no due-date field, no payment-tracking concept at all on `sales_invoice` |
| Sales analysis (by customer/product/category/salesperson/period) | MISSING | no aggregation endpoint beyond the 4 dashboard KPIs |
| Sales margin report | MISSING | `cost_price` exists on `Product` but isn't even exposed via API (§3), so a margin report can't be built without first closing that gap |
| Delivery as a distinct document | OUT OF SCOPE (by original design) | invoicing directly deducts stock (Phase 8 §3's deliberate M2 scope decision) — noted here as a real Odoo-benchmark gap, not silently missing |

---

## 10. Purchasing Gap Analysis

| Feature | State | Evidence |
|---|---|---|
| PO → Receipt → Bill → 3-way match | EXISTING AND WORKING | Verified in Phase 12/16 |
| Vendor card / 360 view | MISSING | same gap as customer card |
| Vendor statement, balance, outstanding bills | MISSING | same due-date/payment gap as Sales |
| Purchase analysis, price history | MISSING | no aggregation endpoint |
| RFQ | MISSING | explicitly out of scope in the original M4 design note — real gap, low priority |

---

## 11. Reporting Gap Analysis

The entire reporting module is 3 endpoints: one dashboard, two CSV
exports. There is no shared reporting architecture at all — each export
hand-builds its own CSV in the route handler
(`reporting/api/routes.py`). Every report requested in §15 (Report
Inventory) is either MISSING outright or would currently require a
bespoke, one-off endpoint with no shared filter/export/permission
pattern to build on.

---

## 12. Core Business Cards

| Card | State |
|---|---|
| Product Card | MISSING — no detail page; `admin/page.tsx` only lists |
| Customer Card | MISSING |
| Vendor Card | MISSING |
| Account Card | MISSING — closest existing analog is the journal-entry detail page, which shows one entry, not one account's full ledger |

None of the four standard ERP "card" screens exist. This is a direct,
compounding consequence of §7–§10's missing statements/history reports —
a card is largely a composition of those reports around one master
record, so building the reports first (or in tandem) is the efficient
order, not building card *shells* first.

---

## 13. End-to-End Business Flows

**Sales**: Quotation → Order → Invoice works completely. → Payment and →
Customer Statement **do not exist as steps at all** — there is no payment
recording endpoint anywhere in the system (confirmed: no `payment` table,
no `POST .../payment` route in any module). An invoice's status can reach
`cleared`/`reported` (ZATCA) but never `paid`.

**Purchasing**: PO → Receipt → Bill works completely. → Payment and →
Vendor Statement have the identical gap as Sales.

**Inventory**: Receipt → Warehouse → Stock Balance → Issue → Stock Balance
works completely and correctly (verified, including the Phase 16B
concurrency fix's scope).

**Accounting**: Invoice → Journal Entry → Customer Receivable works (the
journal entry posts correctly). → Payment → Customer Balance breaks
immediately after the journal entry, for the same reason as Sales: no
payment concept exists anywhere in this system yet.

**This is the single most important cross-cutting finding in this
document**: every business flow in this ERP currently dead-ends at
"invoice/bill posted" — nothing represents a payment being received or
made. AR/AP aging, customer/vendor balances, and both statements are all
downstream of this one missing concept.

---

## 14. Standard ERP Data Relationships (documentation only, per Step 8 — no schema touched)

```
Customer (Partner, is_customer=true)
  → Quotations → Sales Orders → Invoices → [Payments: MISSING] → Statement: MISSING

Vendor (Partner, is_vendor=true)
  → Purchase Orders → Goods Receipts → Vendor Bills → [Payments: MISSING] → Statement: MISSING

Product
  → Category: PLACEHOLDER (column exists, unusable)
  → UOM: MISSING (no table)
  → Warehouse → Location → Stock Moves: WORKING
  → Purchases / Sales history: data exists (queryable via existing tables) but no aggregated view/report exists yet
  → Valuation: WORKING (per-quant), no aggregate report

Account
  → Journal Entries → Ledger: MISSING (only trial-balance aggregate exists)
  → Trial Balance: WORKING
  → Financial Statements (P&L/Balance Sheet): MISSING
```

---

## 15. Report Inventory

Every report from the task's required list, checked against the actual
codebase:

### Inventory Reports
| # | Report | State |
|---|---|---|
| 1 | Stock Balance | PARTIAL — `GET /stock/quants` returns raw data, no report UI/filters |
| 2 | Product Stock Card | MISSING |
| 3 | Stock Movement | PARTIAL — `GET /stock/moves` exists, unfiltered, no report UI |
| 4 | Inventory by Warehouse | MISSING (data groupable from quants, no endpoint does it) |
| 5 | Inventory by Location | MISSING |
| 6 | Inventory by Category | MISSING (blocked on §6) |
| 7 | Inventory Valuation | MISSING |
| 8 | Inventory Count | PARTIAL — cycle count exists, no report view of count history |
| 9 | Inventory Variance | MISSING |
| 10 | Stock Transfer Report | MISSING |
| 11 | Low Stock Report | MISSING (blocked on reorder-level schema gap) |
| 12 | Negative Stock Report | MISSING |
| 13 | Slow Moving Items | MISSING |
| 14 | Product Cost History | MISSING |
| 15 | Stock Aging | MISSING |

### Accounting Reports
| # | Report | State |
|---|---|---|
| 1 | Trial Balance | EXISTING AND WORKING |
| 2 | General Ledger | MISSING |
| 3 | Account Statement | MISSING |
| 4 | Customer Statement | MISSING |
| 5 | Vendor Statement | MISSING |
| 6 | Accounts Receivable | MISSING |
| 7 | Accounts Payable | MISSING |
| 8 | Receivables Aging | MISSING (blocked on payment/due-date schema gap) |
| 9 | Payables Aging | MISSING (same) |
| 10 | Profit & Loss | MISSING |
| 11 | Balance Sheet | MISSING |
| 12 | Journal Register | PARTIAL — `GET /journal-entries` list exists, no report framing (filters/export) |
| 13 | Tax Report | MISSING |
| 14 | Customer Balance | MISSING |
| 15 | Vendor Balance | MISSING |

### Sales Reports
All 12 requested (Sales Register through Sales Order Analysis) are
**MISSING** — the dashboard's "Sales this period" KPI is the only
aggregate sales figure anywhere in the system.

### Purchasing Reports
All 10 requested are **MISSING** — same situation, one dashboard KPI is
the entire purchasing-side reporting surface.

**Summary**: of 52 requested reports across all four areas, **1 is fully
working** (Trial Balance), **3 are partial** (Stock Balance, Stock
Movement, Journal Register — all "raw data endpoint exists, no report
wrapper"), and **48 are missing outright.**

---

## 16. Odoo Benchmark Matrix

| Functional Area | Standard ERP/Odoo Concept | Our Current System | Gap | Priority |
|---|---|---|---|---|
| Product classification | Category tree, UOM, barcode | Category column exists unused; no UOM/barcode at all | Full stack (schema + API + UI) | P0 |
| Customer/Vendor 360 view | Contact form with balance, history tabs | Flat CRUD list only | Full card UI + backing reports | P0 |
| Payments | Register a payment against an invoice/bill, auto-reconcile | Does not exist | New module-adjacent feature (schema + service + UI) | P0 |
| AR/AP Aging | Standard bucketed aging report | Does not exist | Blocked on Payments + due dates | P0 |
| Financial Statements | P&L, Balance Sheet from CoA | Only trial balance | New reporting logic on existing CoA data | P0 |
| General Ledger | Per-account transaction drill-down | Does not exist | New report on existing `journal_entry_line` data | P0 |
| List view UX | Filter/group/sort/export/saved filters | Ad hoc per-module tables | New shared frontend component | P0 |
| RBAC role management | Create/edit roles and permission sets in UI | Enforcement exists, zero management UI | New Identity UI + API | P1 |
| Reordering rules | Min/max stock, auto-PO suggestion | Does not exist | Schema + logic | P1 |
| Sales/Purchase analysis | Pivot-style breakdowns | Does not exist | New reporting endpoints | P1 |
| RFQ | Multi-vendor quote comparison before PO | Does not exist | New Purchasing feature | P2 |
| Delivery as distinct document | Separate picking/delivery step before invoice | Folded into invoice issuance | Architectural change | P2 (deliberate nucleus scope, revisit only if a real customer needs it) |
| Multi-currency | Per-transaction currency + rates | `currency_code` field exists, single-currency in practice | Real but lower-impact for a single-market (SAR) trading company | OUT OF SCOPE for v1 |
| Serial/lot tracking | Per-unit or per-batch tracking | Does not exist | New Inventory concept | OUT OF SCOPE for v1 (not requested by the target business profile) |

---

## 17. Master Gap Matrix

The full matrix (abbreviated to the highest-signal rows here — the
complete report/screen-level detail is already in §7–§10 and §15 to avoid
duplicating ~90 near-identical rows):

| Module | Area | Feature | Current State | Target State | Gap | Priority | Dependencies |
|---|---|---|---|---|---|---|---|
| Master Data | Product | Category assignment | PLACEHOLDER | Full category tree usable in product form + filters | API + UI for `ProductCategory` | P0 | None — table exists |
| Master Data | Product | Unit of Measure | MISSING | Purchase/Sales UOM per product | New table + schema + UI | P0 | None |
| Master Data | Product | Reorder level / min-max | MISSING | Configurable per product/warehouse | New columns + UI | P1 | UOM (for meaningful units) |
| Master Data | Partner | Customer/Vendor card | MISSING | Full 360 view | New page + backing reports | P0 | Statement/balance reports |
| Accounting | Reports | General Ledger | MISSING | Per-account drill-down | New endpoint + UI | P0 | None — data exists |
| Accounting | Reports | P&L / Balance Sheet | MISSING | Standard financial statements | New aggregation logic | P0 | None — CoA/account_type data exists |
| Cross-module | Payments | Payment recording | MISSING | Register payment, update invoice/bill status | New schema + service + UI | P0 | None, but blocks 6+ other reports |
| Accounting | Reports | AR/AP Aging | MISSING | Bucketed aging | Payments + due dates | P0 | Payments |
| UI/UX | List views | Shared filter/sort/export | MISSING | One reusable component | New frontend architecture | P0 | None |
| Identity | RBAC | Role management UI | MISSING | Create/edit roles in UI | New API + UI | P1 | None — enforcement already works |
| Inventory | Reports | Stock Card | MISSING | Per-product ledger | New endpoint + UI | P1 | None — moves data exists |
| Sales/Purchasing | Reports | Analysis reports | MISSING | By customer/product/period | New aggregation endpoints | P1 | Reporting architecture (§20) |
| Purchasing | Workflow | RFQ | MISSING | Multi-vendor quote step before PO | New feature | P2 | None |
| Inventory | Master data | Barcode | MISSING | Scan-friendly lookup | New column | P2 | None |

---

## 18. P0 / P1 / P2 Priorities

Counts (full detail in §17 and the module-level tables in §7–§10, §15):

- **P0 (Essential): 9** — Product category usability, UOM, Customer/Vendor
  card, General Ledger, P&L/Balance Sheet, Payments, AR/AP Aging, shared
  list-view UX, shared report architecture.
- **P1 (Important): 6** — Reorder rules/low-stock, Stock Card, RBAC role
  management UI, Sales/Purchase analysis reports, Statements (customer/
  vendor), Fiscal-period management UI.
- **P2 (Enhancement): 5** — RFQ, barcode, product cost history, slow-moving
  items report, tax report.
- **Out of scope for this release**: multi-currency depth, serial/lot
  tracking, Delivery as a distinct document, CRM/POS/Manufacturing/HR
  (per the task's own explicit instruction).

Not everything is P0 — Payments is the one item that, if delayed, would
silently block 5 other P0/P1 items (aging, statements, customer/vendor
balance, the "balance" tab of both cards), so it is sequenced first among
equals within P0 despite being its own new concept rather than an
extension of existing code.

---

## 19. Standard ERP v1 Definition

For an Electrical/Lighting/Building Materials trading company, "Standard
ERP v1" means a user can, without touching a database console:

1. Classify products into a real category tree with units of measure.
2. Open any customer or vendor and see their balance, outstanding
   documents, and full transaction history in one place.
3. Record a payment against an invoice or bill and see the balance update.
4. Pull an AR/AP aging report before making collection or payment
   decisions.
5. Pull a General Ledger, P&L, and Balance Sheet for any date range.
6. Search, filter, and export any list in the system the same way,
   everywhere.
7. See stock by warehouse/location/category and a single product's full
   movement history.

This is deliberately **not** "match every Odoo module" — it's the
specific set of gaps that, left unclosed, would make this system
unusable for the stated target business, distilled from the evidence
above rather than a generic ERP checklist.

---

## 20. Architecture Recommendations

- **Reporting layer**: introduce a shared query/DTO pattern — a generic
  `ReportFilter` (date range, company/branch, entity references,
  group-by) consumed by every report endpoint, and a generic paginated/
  filterable list response shape reused by every module's list endpoint.
  Today, Sales, Purchasing, Inventory, and Accounting each hand-roll their
  own list query shape — consolidating this before building 48 new
  reports avoids building the same inconsistency 48 more times.
- **Frontend list/table component**: one shared component providing
  search, filter, sort, pagination, column selection, and CSV export,
  replacing each module's bespoke `<Table>` usage. This is the single
  highest-leverage frontend investment — every other screen in this
  document depends on it existing first or the UI stays as inconsistent
  as it is today.
- **Payments as a new lightweight module**, not bolted onto Sales/
  Purchasing — it touches both (customer payments, vendor payments) and
  Accounting (cash/bank journal posting), matching the existing
  one-way-dependency discipline (Payments depends on Identity+Accounting,
  same shape as Sales/Purchasing today).
- **Cards as compositions, not new data**: Product/Customer/Vendor/Account
  cards should be built as frontend pages that call the *already-planned*
  reports (statement, stock card, ledger) rather than inventing new
  bespoke endpoints — sequencing the reports before the cards avoids
  building the cards twice.

---

## 21. Implementation Roadmap

Validated and adjusted from the suggested structure based on actual
dependencies found in this audit — Payments is pulled forward because
so much else depends on it, and the UI design system is pulled forward
because building six more modules' worth of screens on the current
ad hoc pattern would compound the exact problem this phase exists to fix.

### Phase 17A — UX/UI Design System (P0)
Shared list-view and report-filter components, shared form-view
conventions. No new business features — infrastructure every subsequent
phase builds on.

### Phase 17B — Master Data + Product Classification (P0)
`ProductCategory` API/UI, Unit of Measure (new schema), category
assignment on the product form, Partner detail fields (address exposure).

### Phase 17C — Payments (P0, pulled forward)
New minimal payment-recording schema/service/UI for both customer and
vendor payments, posting the matching cash/bank journal entry. Chosen
before Accounting/Sales/Purchasing standardization because those phases'
reports (aging, statements, balances) are otherwise unbuildable.

### Phase 17D — Accounting Standardization (P0)
General Ledger, P&L, Balance Sheet, AR/AP Aging (now unblocked by 17C).

### Phase 17E — Sales & Purchasing Standardization (P0/P1)
Customer/Vendor cards and statements (built on 17C/17D's data), sales
and purchase analysis reports (P1).

### Phase 17F — Inventory Standardization (P1)
Stock card, reorder rules, low-stock alerts, inventory-by-category
(unblocked by 17B).

### Phase 17G — Cross-module Reporting Polish (P1/P2)
Remaining analysis reports, tax report, slow-moving items, cost history.

### Phase 17H — RBAC Role Management UI (P1)
Independent of the above — can run in parallel with 17D–17G once 17A's
shared UI components exist.

**Dependency chain, explicitly**: 17A blocks everything (shared UI). 17B
blocks inventory-by-category and meaningful product cards. 17C blocks
aging, statements, and the "balance" portion of both cards. 17D depends
on 17C. 17E depends on both 17C and 17D. 17F only depends on 17B. 17G
depends on 17A's reporting architecture but not on 17C/D/E directly. 17H
is independent.

---

## 22. Acceptance Criteria

A user can, in Standard ERP v1:

- Create a product category tree and assign products to it.
- Define a unit of measure and select it on a product.
- Open a Customer Card showing balance, outstanding invoices, and
  transaction history.
- Open a Vendor Card showing the same, vendor-side.
- Record a customer payment against an invoice and see its status/balance
  update.
- Record a vendor payment against a bill, same effect.
- Pull a Receivables Aging and a Payables Aging report.
- Pull a General Ledger for any account and date range.
- Pull a Profit & Loss and a Balance Sheet for any date range.
- Search, filter, sort, and export any list screen in the system using
  the same UI pattern.
- View a single product's full stock movement history (Stock Card).
- See a low-stock warning for a product below its configured reorder
  level.
- Do all of the above in both Arabic (RTL) and English (LTR).

Each item above maps to a specific P0/P1 gap in §18 — nothing here is
aspirational beyond what's already scoped and sequenced.

---

## 23. Risks / Dependencies

- **Payments touches accounting posting logic directly** — the same
  class of risk Phase 16B just spent real effort closing (duplicate
  postings, race conditions). 17C must apply the same idempotency/
  locking discipline from day one, not retrofit it later.
- **Schema changes required** (UOM, category exposure, product
  min/max/reorder, due dates on invoices/bills) mean 17B/17C/17D all need
  real migrations, not just new UI — likely to interact with existing
  RLS policies (Phase 16A pattern: new tables need `company_id` + policy
  from the start, not bolted on after).
- **Frontend component investment (17A) has no visible feature output on
  its own** — real risk of pressure to skip it and go straight to
  features, which is exactly how the current ad hoc pattern happened in
  the first place.
- **The "Delivery as a distinct document" gap is architectural**, not a
  screen — revisiting it later would touch Sales' core invoicing flow;
  flagged as out-of-scope now specifically so it isn't accidentally
  half-implemented as a side effect of 17E.

---

## 24. Explicit Out-of-Scope Items

Per the task's own instruction, and confirmed by this audit to have no
forcing dependency from the current architecture:

- CRM, POS, Manufacturing, HR/Payroll, Projects, Construction Management
- Multi-currency depth (multiple active currencies with live rates)
- Serial/lot/batch tracking
- RFQ (multi-vendor quote comparison) — P2, not v1
- Delivery as a distinct document from invoicing — architectural,
  deliberate nucleus-era decision, not revisited in this release
- ZATCA production certification — separate, previously-scoped Phase 16
  item, unrelated to ERP standardization
