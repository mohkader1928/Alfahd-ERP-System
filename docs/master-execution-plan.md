# MASTER EXECUTION PLAN

**Prepared by:** Contractor (Claude Code) — for Owner review, with Consultant (ChatGPT) available for a second opinion on any architectural point below.
**Date:** 2026-08-02 (updated across several same-day governance instructions; latest update: methodology/UX/reporting/traceability governance rules, no code changed)
**Trigger:** Owner directives, in order: "PROJECT EXECUTION DIRECTIVE — OWNER / CONSULTANT / CONTRACTOR MODE" → "MASTER EXECUTION DIRECTIVE — Milestone 0" → "MASTER EXECUTION DIRECTIVE — Owner / Consultant Controlled Execution" (Milestone 1a delivery + commit) → "Owner Acceptance Checkpoint — Milestone 1a" (hands-on test environment) → the current governance update (Section D3, Rule 0 in Section G, UX north-star, Standard Report Catalog).
**Status:** Living plan, updated at every checkpoint. Milestone 0 and Milestone 1a are done and committed. Milestone 1a's Owner Acceptance environment is ready and awaiting the Owner's own test. No Milestone beyond 1a has started. Section D3 and Rule 0 (Section G) are new, planning-only additions from this update — no application code was touched to produce them.

> A few terms recur through this document. **RLS (Row-Level Security)** = a database feature that automatically hides other companies' data from every query, enforced by Postgres itself, not by application code (so even a bug in the code can't leak data across companies). **Migration** = a versioned, scripted change to the database structure (e.g., "add a column"), applied in order, always reversible in principle. **Idempotent** = running the same script twice produces the same result as running it once — nothing doubles up. **Endpoint** = one URL the backend exposes, e.g. `GET /payments`. Other terms are explained inline the first time they appear.

---

## A. Current Reality — what actually works right now

**Last commit:** `3684edd` — "fix: harden database runtime role and RLS enforcement" (Phase 17C-RLS). Everything after that point (Phase 17D — Payments) is implemented, tested, and browser-verified, but **sitting uncommitted** in the working tree (24 files: 13 modified, 11 new). Nothing has been lost or reverted; it is simply waiting for the commit step, which this plan recommends as Milestone 0.

**Architecture today:** A modular monolith — one FastAPI backend, one Next.js frontend, one Postgres database — with modules kept in one-way dependency order (Identity → everything; Accounting is consumed by Sales/Purchasing/Inventory/Payments but never calls back out to them). This is deliberate and matches the Owner's instruction not to introduce microservices or event buses at this stage.

**Security foundation (Phase 17C-RLS):** Every business table is owned by a migration-only database role and enforces RLS with `FORCE ROW LEVEL SECURITY`. The API and background worker run 100% of live traffic through a restricted role (`erp_app`) that cannot bypass RLS and cannot alter schema. This was verified, not assumed — 24/24 RLS tests plus a full regression pass. **This is the single most important thing already built: multi-company data isolation is real, database-enforced, and independent of application code correctness.**

**What a real user can do in the system today, end-to-end, from the UI:**

| Business capability | Can an Owner/user do this today from the screen, start to finish? |
|---|---|
| Log in, pick a company, manage users/roles | Yes |
| Create a Customer, Vendor, Product, Category, Unit of Measure | Yes |
| Sales: Quotation → confirm to Sales Order → Delivery → Invoice (incl. ZATCA sandbox e-invoicing) → Credit Note | Yes |
| Purchasing: Purchase Order → Receiving → Vendor Bill | Yes |
| Record a Payment (customer or vendor) against a real invoice/bill, with a live outstanding-balance picker | Yes (Phase 17D, pending commit) |
| Inventory: Warehouses, stock levels, receive stock, transfer between locations, cycle count | Yes |
| Accounting: Chart of Accounts, manual Journal Entries, Trial Balance | Yes, but manual entry only — no month-end/reporting workflow beyond Trial Balance |
| See a Customer's or Vendor's running balance / statement | **No** — the only balance view is per-document ("this invoice has 130 SAR left"), not a partner-level statement |
| See Income Statement or Balance Sheet | **No** — not built |
| See AR/AP Aging (who owes what, how overdue) | **No** — not built |
| Filter/search/export a report with real business filters (date range, customer, status) | **Mostly no** — Reporting module is limited to a few flat CSV exports, no interactive filter UI |
| Cancel a confirmed document (order, invoice, bill) | **No** — no cancel endpoint exists anywhere in the system despite "cancelled" being a valid status value in several places |
| See an audit trail of who changed what | **Almost never** — only 3 places in the entire codebase write an audit log entry |

**Testing/quality gates today:** ~141 backend tests (130 pre-Payments + 11 new Payments tests), Ruff, mypy-equivalent type checks, TypeScript, ESLint, and the frontend build all pass clean as of the last verification pass. Docker cold-restart and `/health` were verified. This is a real, evidence-based baseline — not an estimate.

**Demo data today:** None, beyond what a developer creates ad hoc while testing. This is a real gap for an Owner who wants to click around and see a populated system, and is addressed in Section F below.

---

## B. Completed Roadmap — in order

1. Initial commit — core nucleus (Identity, base module scaffolding, Docker, CI baseline).
2. CORS hardening fix (environment-driven origins).
3. Phase 16B — idempotency & concurrency design (prevented duplicate invoice creation via a database constraint; established the "prove it under a real concurrent test, don't just reason about it" discipline used again in Payments).
4. Phase 17A — UX/UI Design System foundation (shared list view, form view, table components, i18n scaffolding).
5. Phase 17B — Master Data standardization (Products, Categories, UOM, Customers/Vendors on the shared design system).
6. Phase 17C-RLS — database runtime role & Row-Level Security hardening (unplanned, pulled forward for security reasons; this is why the naming below has a gap).
7. Phase 17D — Payments (implemented and re-audited against real business scenarios: full payment, partial payment, overpayment rejection, vendor payment, cross-company isolation, concurrent-request race protection with a real proof test). **Verified complete. Not yet committed** — recommended as Milestone 0 below.

---

## C. Remaining Roadmap — what's left until project completion

**Near-term (this document's planning horizon — the "Business Core"):**

- Accounting Standardization — Income Statement, Balance Sheet, AR/AP Aging, General Ledger drill-down, Customer/Vendor statements (see Section D — this is the direct next dependency, now unblocked by Payments).
- Sales & Purchasing Standardization — customer/vendor statement screens, sales/purchasing history views, basic filterable reports.
- Inventory Standardization — stock valuation report, low-stock/reorder visibility, inventory history report.
- Reporting Polish — turn the existing flat CSV exports into real, filterable, cross-module report screens.
- RBAC Role Management UI — currently roles/permissions exist in the data model and are enforced, but there is no screen for an Owner to manage them without developer help.

**Further out (explicitly out of scope until the Business Core is complete, per Owner directive):** Manufacturing, HR, Projects/Construction, POS, E-Commerce, BI/Analytics, AI features. These remain on the original blueprint but are not touched until Section D's gap list is closed.

### C2. Roadmap dependency detail — each remaining phase

| Phase | Dependencies | Key deliverables | Acceptance criteria | Est. duration (Dev) | Major risks |
|---|---|---|---|---|---|
| **M0 — Baseline & Governance** (this document) | None | This plan, UX standard doc, updated progress doc | Owner approval | Same session | None — pure audit/planning |
| **M1a — General Ledger, Income Statement, Balance Sheet** | Payments (M0) committed; Journal Entry posting already correct | GL per-account drill-down, Income Statement (Revenue/COGS/OpEx/Net Income via existing CoA hierarchy), Balance Sheet (provably `Assets = Liabilities + Equity`) | Scenario #7 in Section D2 passes live | **Done** — 6 new tests, 147/147 suite, live-verified; see `docs/17e-accounting-standardization.md` | Reconciled cleanly against real posted JEs; no discrepancy found |
| **M1b — Customer/Vendor Subledgers + AR/AP Aging** *(scope clarified 2026-08-02, §D3.2 — was "Aging + Statements", now explicitly full subledgers)* | M1a; Payments' existing balance logic; Sales/Purchasing due dates (Phase 17D) | Real Customer Subledger and Vendor Subledger (opening balance → invoices/credit notes/payments/adjustments → running balance → closing balance, each line drillable to source, §D3.1), plus AR/AP Aging buckets | Subledger closing balance matches Accounting's own AR/AP balances exactly; every subledger line opens its real source document | **Done** — 13 new tests, 159/159 suite, live-verified; see `docs/17f-subledgers-and-aging.md` | Reconciled cleanly against real posted data (direct assertion test); one real correctness bug found and fixed during verification, not shipped silently (17f doc §5); one structural RBAC finding documented, not fixed (17f doc §7) |
| **M2 — Reporting Polish** | M1 (reports need real Accounting views to link to) | Filterable Sales/Purchasing/Inventory report screens wired to real data | Owner can filter by date/customer/status and get correct results | 3–5 days | Risk of becoming a second, disconnected reporting path if not built against M1's views (see Section J) |
| **M3 — Demo Data Mechanism** | M2 (so reports have data worth seeding) | Idempotent seed script, ~100 records/type, transactional spread (Section F) | Script reruns cleanly; Owner sees a populated system end to end | 2–3 days | Must go through service layer under RLS — slower than raw SQL, non-negotiable per Owner directive |
| **M4 — Sales/Purchasing Standardization** | M1 (statements need Accounting views) | Customer/Vendor statement screens, history views, cancel-workflow decision | Statements match Accounting's own AR/AP figures exactly | 3–5 days | Cancel/void is a real scope decision, not just UI — must be explicitly scoped at this Milestone's checkpoint, not assumed |
| **M5 — Inventory Standardization** *(scope expanded 2026-08-02, §D3.2)* | M1 (valuation ties to Accounting) | Stock valuation report, low-stock view, movement history, **Inventory Item Subledger** (item+warehouse, opening/closing qty, all movement types, drillable to source) | Valuation report reconciles with Accounting's Inventory account balance; every subledger line opens its real source document | 3–5 days *(was 2–4; increased for the subledger)* | Valuation method consistency (the system already supports a configured method — must not introduce a second one) |
| **M6 — UX Consistency Pass + RBAC Role Management UI** | M4/M5 (needs stable screens to make consistent); UX standard doc (this Milestone) | Formatting utility, notification/toast system, permission-gating audit, Role Management screen | Matches `docs/erp-ux-standard.md` §2 gap list, item by item | 2–3 days | Must not turn into an open-ended redesign — scoped strictly to the gap list already identified |

---

## D. Business Core Gap Analysis

The Owner's standard is explicit: Sales + Purchasing + Inventory + Accounting + Reports must work **together**, not just individually. Below is what's missing to call that true, module by module.

### Sales
- Have: Quotation → Order → Delivery → Invoice → Credit Note → Payment, all posting to Accounting, all under RLS.
- Missing: a Customer Statement screen (list of a customer's invoices/payments/running balance in one place); a Sales History/report screen with real filters (date range, customer, status); no "cancel" path for a confirmed order.

### Purchasing
- Have: Purchase Order → Receiving → Vendor Bill → Payment, posting to Accounting.
- Missing: same gap mirrored — Vendor Statement screen, Purchase History report with filters, no "cancel" path.

### Inventory
- Have: Warehouses, stock levels, receiving, transfers, cycle counts, all correctly moving stock and (where applicable) cost.
- Missing: a stock valuation report (total inventory value by warehouse/category), a low-stock/reorder visibility view, an inventory movement history report with filters.

### Accounting
- Have: Chart of Accounts, manual Journal Entries, Trial Balance, and — critically — every Sales/Purchasing/Payments transaction already posts correct, balanced journal entries automatically. This is the hardest part and it already works.
- Missing: Income Statement (profit/loss over a period), Balance Sheet (financial position at a point in time), AR/AP Aging (who owes money, how overdue), General Ledger drill-down (click an account, see every transaction that hit it). **This is the single largest gap blocking the Owner from actually running the business through the system**, because right now the only way to answer "what do we owe / what are we owed / are we profitable" is to read raw Journal Entries.

### Reports
- Have: A handful of flat CSV exports.
- Missing: real screens with the filters the Owner directive specifically calls for (date range, company, customer/supplier, product, status, search, sort, pagination, drill-down). Currently reports are not "reports" in the usable sense yet — this is accurately reflected in `docs/project-progress.md` at 🔴15%.

### Cross-cutting gaps affecting all of the above
- No audit trail worth relying on (3 call sites total).
- No maker-checker/approval workflow anywhere, despite several documents (Purchase Orders, Vendor Bills) having states that imply one.
- No "cancel" endpoint anywhere in the system.

**Conclusion:** the transactional backbone (Sales↔Inventory↔Accounting↔Payments) is real and proven end-to-end. What's missing to call this a usable Business Core is almost entirely on the **reporting and statement side** — the system correctly records everything but doesn't yet show the Owner the summarized business answers. That is why Accounting Standardization (Income Statement/Balance Sheet/Aging/GL drill-down) is recommended as the next milestone: it closes the biggest, highest-value gap first.

---

## D2. Business Core — Definition of Done & Acceptance Scenarios

This section answers directly: **what has to be true before Sales + Purchasing + Inventory + Accounting + Payments + core Reporting can be called one accepted, integrated product?**

### Definition of Done (Business Core level)

The Business Core is Done only when every item below is true — not when the last screen is coded:

1. Every module in scope (Sales, Purchasing, Inventory, Accounting, Payments, Reporting) has passed its own Milestone-level Definition of Done (Section H).
2. Every cross-module business scenario in the table below has been executed for real (not just unit-tested) and produced the correct result in every downstream module it touches.
3. `docs/project-progress.md` shows no module in this list below "Partially Completed" for a reason that blocks a scenario in the table.
4. Demo data (Section F) is loaded and every scenario below is repeatable by the Owner from the UI using that data, without developer help.
5. Regression suite (141 backend tests today, growing) still passes in full, plus RLS/company-isolation tests specific to any new tables.
6. The Owner has personally run at least the "core proof" scenarios (marked ✅ required) at a live Owner Checkpoint and accepted the result.

### Acceptance scenarios (this is the actual test of "integrated," not "module complete")

| # | Scenario | Proves | Required for core acceptance? |
|---|---|---|---|
| 1 | Create Customer → Quotation → Sales Order → Delivery → Invoice → Payment (full) → check Journal Entry, AR, Customer Statement, Sales Report all reflect it | Sales↔Accounting↔Payments↔Reporting integration | ✅ required |
| 2 | Same as #1 but Payment is **partial** → Customer Statement shows outstanding balance, invoice status is `partially_paid`, AR is correct | Partial-payment correctness end-to-end | ✅ required |
| 3 | Create Supplier → Purchase Order → Receipt → Vendor Bill → Payment → check Journal Entry, AP, Vendor Statement, Purchasing Report | Purchasing↔Accounting↔Payments↔Reporting integration | ✅ required |
| 4 | Sales Delivery reduces stock; Purchase Receipt increases stock; both reflected correctly in Inventory's stock-on-hand and in Accounting (COGS/Inventory account) | Inventory↔Accounting integration | ✅ required |
| 5 | Warehouse-to-warehouse Transfer; Cycle Count with a variance, corrected via Adjustment | Inventory internal correctness | ✅ required |
| 6 | Two companies (tenants) each run scenario #1 independently — confirm zero data crossover anywhere (lists, statements, reports, balances) | RLS/company isolation under real business use, not just direct-table tests | ✅ required |
| 7 | Open Trial Balance, Income Statement, Balance Sheet, AR Aging, AP Aging after the above scenarios and confirm the numbers match what was entered | Accounting Standardization (Milestone 1) delivers real answers, not just screens | ✅ required (blocks on Milestone 1) |
| 8 | Concurrent payment attempts against the same invoice — confirm exactly one succeeds and the balance is never over-allocated | Data integrity under real concurrent use (already proven for Payments specifically; re-run as part of core acceptance, not re-designed) | ✅ required |

Scenarios 1–6 and 8 can be run **today** once Phase 17D is committed (Milestone 0). Scenario 7 is blocked on Milestone 1 (Accounting Standardization) by design — this is precisely why Milestone 1 is the recommended next body of work.

---

## D3. Cross-Cutting Requirements (Governance Update, 2026-08-02)

The Owner formalized four standing requirements that apply across every future Milestone, not to any single one. They don't change anything already shipped and don't conflict with the current architecture — they are additive constraints future work must satisfy. Recorded here so they are never silently forgotten while a specific Milestone is being planned.

### D3.1 System-wide traceability ("every number has a source")

**Principle**: `Transaction → Source Document → Accounting → Subledger → Report`, traceable in both directions, everywhere a document reference or number appears. If a screen shows an invoice number, a Journal Entry reference, or a stock movement, it must be clickable through to that real record — never a bare UUID or a dead label.

**Where this already exists** (proven, not aspirational): Payments' invoice/bill picker resolves to real names, not IDs (Phase 17D); General Ledger's Reference column links to the real Journal Entry (Milestone 1a, live-verified). **Where it does not exist yet**: Sales Order ↔ Invoice, Purchase Order ↔ Vendor Bill, and any Inventory movement back to the document that created it. This gap is not new — it was already listed in `docs/erp-ux-standard.md` §12 ("Document lifecycle & related documents") — the Owner has now elevated it from a nice-to-have to a **required property of every future Milestone's Definition of Done**, per §H below.

### D3.2 Subledgers — this reshapes Milestone 1b and Milestone 5

The Owner's requirement is for real Customer/Vendor/Inventory-Item **subledgers** (opening balance, every movement type, running balance, closing balance, drill-down to source) — not just an aging bucket table. This is a genuine scope clarification, recorded transparently rather than silently absorbed:

- **Milestone 1b** (previously scoped in §C2 as "AR/AP Aging, Customer/Vendor Statements") now explicitly includes full **Customer Subledger** and **Vendor Subledger** reports (opening balance → invoices/credit notes/payments/adjustments → running balance → closing balance, each line drillable to its source document) — Aging remains part of 1b, but the subledger view is the richer, primary deliverable it was always meant to feed.
- **Milestone 5** (Inventory Standardization) now explicitly includes an **Inventory Item Subledger** (item + warehouse, opening qty → receipts/issues/transfers/adjustments/returns → closing qty, with unit cost/value where available, each line drillable to its source: Purchase Receipt, Sales Delivery, Transfer, Adjustment, Return).

Both were already directionally implied by the original blueprint's "Customer/Vendor cards + statements" and "Stock card" items (§C's DEFERRED bucket in `docs/project-progress.md`) — this update makes the acceptance bar for both explicit rather than leaving "statement" ambiguous between a summary and a real subledger.

### D3.3 Standard ERP Report Catalog (reference, not a build list)

The Owner supplied a full catalog of reports a professional ERP user expects per module (Accounting, Sales, Purchasing, Inventory — full list below). **This is an architectural/functional checklist to consult when scoping each future Milestone, not a mandate to build all of it now.** Recorded in full so it isn't lost between checkpoints:

| Module | Standard reports to check against when scoping that module's Milestone |
|---|---|
| **Accounting** | Trial Balance ✅, General Ledger ✅, Customer Subledger (M1b), Vendor Subledger (M1b), Customer Statement (M1b), Vendor Statement (M1b), AR Aging (M1b), AP Aging (M1b), Income Statement ✅, Balance Sheet ✅, Cash Flow, Journal Register, Account Activity, Tax/VAT Reports, Payment Register, Receipts/Disbursements, Bank/Cash reports, Period comparison |
| **Sales** | Sales Register, Sales by Customer, Sales by Item, Sales by Salesperson, Sales by Date, Sales by Branch, Customer Statement (M1b), Customer Balance, Sales Invoice Register, Credit Note Register, Sales Returns, Sales Order Status, Outstanding Sales Orders, Sales profitability (data-dependent) |
| **Purchasing** | Purchase Register, Purchases by Vendor, Purchases by Item, Vendor Statement (M1b), Vendor Balance, Vendor Bill Register, Purchase Returns, Purchase Order Status, Outstanding Purchase Orders, Vendor performance (data-dependent) |
| **Inventory** | Stock On Hand, Inventory Valuation, Inventory Item Subledger (M5), Stock Movement, Stock Ledger, Warehouse Stock, Item Movement, Inventory Adjustments, Transfers, Stock Aging (data-dependent), Slow/Fast Moving Items (data-dependent), Negative Stock Exceptions, Lot/Serial reports (not yet in scope — no lot/serial tracking exists) |

(✅ = already shipped and live-verified as of Milestone 1a.) This table will be revisited at the start of every Reporting-adjacent Milestone (1b, 2, 4, 5) to check nothing standard was missed — it is not itself a task list to execute sequentially.

### D3.4 Company identity & system entry — flagged for an Owner/Consultant decision, not decided here

Two related asks: (1) the active company's name must be visible everywhere it matters (header, dashboard, documents, reports, print/export, PDF) — this is a straightforward UX gap-check to fold into the Milestone 6 UX consistency pass; (2) a **single desktop icon** that opens the system straight to Login → Owner user → company picker → into that company's context.

Item (2) is **not decided here** because it is a genuine architecture question, not a UX tweak: this is currently a browser-based web app with no native shell. "One desktop icon" could mean (a) a plain browser shortcut/bookmark to the login URL (zero new engineering), (b) a installable Progressive Web App (a browser feature, small manifest/service-worker addition, gives a real desktop/taskbar icon), or (c) a packaged native desktop wrapper (e.g. Electron) — a materially bigger addition of a new build target and packaging pipeline. Per the Owner's own rule (§10/§16 of the governance update: no new frameworks without justification, no big architectural decision made unilaterally), **this needs an explicit Owner/Consultant choice between (a)/(b)/(c) before any of it is scoped into a Milestone.** Recorded here as an open question, not an assumption.

### D3.5 Engineering decision priority (governance update, 2026-08-02)

When more than one implementation approach exists for a future requirement, the choice is made in this order, not by which option uses more of the original blueprint's technology list: **(1) Business correctness, (2) Data integrity, (3) Security, (4) Maintainability, (5) Scalability, (6) Least complexity that satisfies 1–5.** No new framework, service, or pattern is added just because it was named in the original blueprint — it must be justified against this list. This generalizes the rule already in effect since Milestone 0 ("no microservices, Kafka, full CQRS, Kubernetes... the current architecture is a Modular Monolith and that is the foundation").

---

## E. UX Roadmap (parallel workstream, not blocking Business Core work)

**North star (Owner directive, 2026-08-02): Minimum clicks + Minimum typing + Maximum clarity.** Every UX pass below is judged against this, not against how many features it adds.

Runs alongside the Business Core work, one small pass per checkpoint rather than a big separate phase:

1. **Design language audit** — catalogue every list/form/table/filter/select/badge/dialog pattern currently in use across Sales, Purchasing, Inventory, Master Data, Payments; identify the 1–2 modules that drifted from the Phase 17A design system (Payments' new picker introduced a dependent-select pattern worth reusing elsewhere).
2. **Speed-of-entry pass** on the highest-traffic forms first: Customer/Vendor create, Sales Order, Purchase Order, Invoice, Payment — smart defaults (today's date, last-used warehouse/account), searchable selects everywhere an ID is picked, fewer required clicks.
3. **Consistency pass** on status badges, empty states, loading states, and error messages — currently inconsistent module-to-module.
4. **Reusable components** promoted from what Payments already built (the balance-aware dependent picker) into the shared component library so future modules don't reinvent it.
5. **Company identity visibility pass** (new, §D3.4) — audit header/dashboard/document/report/print/export screens for where the active company's name is missing or unclear, and fix it using the existing shared components (no new pattern needed for this part — only the desktop-entry/company-picker question in §D3.4 is an open architecture decision, not this item).
6. **Traceability/drill-down pass** (new, §D3.1) — as each module's own Milestone ships, its documents get real, clickable links to related documents (Order↔Invoice, PO↔Bill, movement↔source), following the exact pattern already proven in Payments and General Ledger, not a new one.

This workstream is explicitly secondary to Business Core completion and will ride along with each Milestone below rather than consume its own dedicated phase.

---

## F. Demo Data Plan

**Requirement:** an Owner who is not a developer needs to open the system and see a realistic, populated business — not empty lists.

### Architecture decision (made now, in Milestone 0 — not implemented yet)

- A dedicated seed script, `backend/src/scripts/seed_demo_data.py`, invoked explicitly and manually (`python -m src.scripts.seed_demo_data`) the same way `bootstrap_db_roles.py` already runs — **never automatic on container startup**, so it can never accidentally run against a production database.
- **Idempotent by natural key**: every record is created with a "look up by business key, then create if missing" pattern (e.g., a customer named "Al-Faisal Trading Co." is looked up by name+company before insert) — running the script twice never duplicates and never errors. This is what "rebuildable" means concretely: delete the demo company, rerun the script, get the same clean dataset back.
- **Goes through the normal application/service layer, not raw SQL** — it runs as `erp_app` (the restricted database role) and passes through the same validation, journal-posting, and RLS-context rules every real user transaction does. No superuser, no business-rule bypass — the same guarantee already proven for every other write path in the system.
- **Isolated to a dedicated demo company/tenant**, never mixed into a tenant a real user is also using — so "reset demo data" can never touch anything else.
- **Why this isn't being built yet:** generating ~100 realistic bilingual master-data records plus a transactional spread across every status (Section F below) is real, multi-day work in its own right, and the directive itself says not to expand scope inside Milestone 0. Building it now, before Milestone 1 (Accounting Standardization) ships, would also mean the demo data can't yet exercise the new reports it needs to prove out. It is scheduled as **Milestone 3** (Section I), immediately after Reporting Polish, for that reason — this is an explicit, reasoned sequencing decision, not a deferral for its own sake.

### Scope (to be built in Milestone 3)

**Master data (~100 records per group, Arabic + English, realistic Saudi business names/addresses, no real personal data):**
Customers, Suppliers, Products (across several Categories), Units of Measure, Warehouses, Locations/Bins (where the model supports them), Chart of Accounts (already seeded — reused, not duplicated), Taxes (VAT rates already modeled — reused), Payment methods/cash-bank Accounts, and the minimum Users/Roles needed to demonstrate RBAC (e.g. a Sales user, a Purchasing user, an Accountant, an Owner/Admin).

**Transactional data**, spread across every status the Owner directive names (Draft, Confirmed, Completed, Partially paid, Fully paid, Outstanding, low-stock, multiple warehouses, multiple dates):
- Sales: Quotations, Orders, Deliveries, Invoices, Credit Notes, Payments.
- Purchasing: Purchase Orders, Receipts, Vendor Bills, Payments.
- Inventory: Receipts, Deliveries (as a byproduct of Sales/Purchasing above), Transfers, Adjustments, Cycle Counts.
- Accounting: the Journal Entries that fall out of all of the above automatically (not separately authored) — this is itself a test that the posting logic is correct across a realistic volume, not just the handful of transactions used in automated tests today.

**Acceptance for Milestone 3 specifically:** the Owner can run the seed script once, see ~100 of each master-data type and a transactionally-consistent spread of the above, rerun the script and get the same result, and the dashboards/reports built in Milestones 1–2 show real, non-empty numbers.

---

## G. Owner Checkpoint Protocol

This is now a formal, standing rule for every Milestone from here forward, not a one-off practice.

### Rule 0 (Governance update, 2026-08-02): the Contractor never self-selects the next Milestone

A checkpoint report never ends with "Next Milestone is X, so I will start X." It ends with a factual status statement and an explicit stop: *"Milestone X is finished; here is its state; here is what remains open; I am stopped, waiting for Owner direction."* Section K below ("Next Execution Milestone") is kept as a **candidate/dependency note for the Owner's own decision**, not as a self-issued go-ahead — the Contractor may name what is technically unblocked next, but must not begin it without an explicit instruction.

### The cycle

**EXECUTE → VERIFY → STOP → REPORT → OWNER DIRECTION**

(Previously written as "...→ OWNER ACCEPTANCE → CONTINUE" — the cycle itself is unchanged, this just makes explicit that "continue" is never assumed from silence or from the report's own recommendation; it requires the Owner's next instruction.)

- **EXECUTE**: build the Milestone's scope, and only that scope.
- **VERIFY**: run the QA/Acceptance Strategy (Section H) — tests, lint, type checks, build, a live browser walkthrough of the real business scenario, Docker health, migration head.
- **STOP**: work halts. No new Milestone starts. No further scope is added, even if a natural next step is obvious.
- **REPORT**: deliver the checkpoint report (template below) in the chat, in the Owner's language, with technical terms briefly explained on first use.
- **OWNER ACCEPTANCE**: the Owner (with the Consultant's input if wanted) reviews and explicitly approves, requests changes, or rejects.
- **CONTINUE**: only after explicit approval does the next Milestone's EXECUTE step begin.

There is no path from EXECUTE directly to CONTINUE. A Milestone that "looks done" is not a Milestone that has been accepted.

### Checkpoint report template (required structure, every time — updated 2026-08-02)

**A. What was done** — concretely, not "Payments module done" but the specific capabilities delivered.
**B. What was tested** — automated test counts and results, by name.
**C. What was verified live** — re-checked independently this checkpoint (re-querying an endpoint after a UI action, a real browser walkthrough) — not assumed from a prior checkpoint's evidence.
**D. What the Owner can try right now** — a real login, real company, real test data, click-by-click steps, the expected result, and what specifically to check to confirm it's genuine (per Section B below).
**E. What remains** — for this Milestone specifically, anything descoped or deferred within it.
**F. Risks** — everything known and not yet resolved, honestly, even if minor.
**G. Full roadmap status** — where this leaves the Global Roadmap Status table and the Timeline (Section I); any reordering or scope change to a future Milestone must be shown here with its reason, never silently.
**H. Files and commits changed** — exact list, exact hashes.
**I. Tests and results** — what was actually run, not just "tests passed."
**J. What needs Owner Acceptance** — named explicitly; nothing on this list is to be treated as accepted until the Owner has tried it and said so.

Then: **STOP.** Per Rule 0 above, the report ends with the project's current state and open items — never with an announcement that the next Milestone is starting.

### A rule about language in these reports

Every report distinguishes explicitly between: **Implemented** (code exists) → **Tested** (automated tests pass) → **Verified** (manually/independently re-checked this checkpoint) → **Live demonstrated** (walked through in a real browser session) → **Owner accepted** (the Owner has actually tried it and said yes) — and, for anything not being pursued right now: **Deferred** (in scope eventually, not now, with a reason) vs. **Known Limitation** (a real, standing gap that isn't blocking, documented so it isn't rediscovered) vs. **Out of Scope** (not planned for this project phase at all). "Completed" is never used as a catch-all when a feature hasn't actually been tested or accepted.

The next checkpoint after this plan is approved will be **Milestone 0 itself** (this document plus the governance artifacts it produced) — see Section K and the final report delivered alongside this plan.

---

## H. QA/Acceptance Strategy

Every Milestone is accepted only when all of the following are true, matching the Owner's Definition of Done (Implemented + Tested + Integrated + Usable + Verified + Documented):

1. Relevant backend tests added (unit + integration, RLS test if new tables are touched, a concurrency test if the feature has a race-condition risk — as was done for Payments).
2. Full backend suite, Ruff, type checks, ESLint, TypeScript, and frontend build all pass clean.
3. A real end-to-end business scenario is walked through live in the browser (not just an API call) and the result is independently re-verified (e.g., re-querying a balance endpoint after a UI action, the same discipline used in Phase 17D).
4. Docker cold restart + `/health` + Alembic migration head confirmed.
5. `docs/project-progress.md` updated; the phase's own doc created/updated.
6. Git diff scope reviewed and reported before commit — no unrelated files.
7. Report delivered in the Owner's checkpoint format (Section G) and **approval received** before moving on.

---

## I. Timeline

Three numbers are given for each Milestone, matching the Owner directive's own distinction:
- **Development** — code written, automated tests passing, ready to demonstrate.
- **Verification** — the Contractor's own live browser walkthrough, regression suite, Docker/health checks (Section H) completed.
- **Owner Acceptance** — the Owner has personally tried it and approved it. **This is the number that actually counts as "done."**

Ranges reflect real uncertainty, not false precision, and assume the working pace already observed in this project (single-Contractor, iterative, checkpoint-gated, no shortcuts on verification).

| Milestone | Development | Verification (adds) | Owner Acceptance (adds) | Depends on |
|---|---|---|---|---|
| **M0 — Baseline & Governance** | done (this document) | done (fresh 141/141 tests, lint, health — same session) | pending — this checkpoint | none |
| **M1a — General Ledger, Income Statement, Balance Sheet** | done | done (147/147 suite, live-verified) | pending — Owner Acceptance environment ready, awaiting Owner's own test | M0 |
| **M1b — Customer/Vendor Subledgers, AR/AP Aging** *(scope expanded, §D3.2)* | done | done (159/159 suite, live-verified, one real bug found+fixed during this pass) | pending — Owner Acceptance environment ready (`docs/owner-acceptance-m1b.md`), awaiting Owner's own test | M1a |
| **M2 — Reporting Polish** | 3–5 days | +0.5–1 day | +1–2 days | M1 |
| **M3 — Demo Data Mechanism** | 2–3 days | +0.5 day | +1 day (Owner test-drives populated system) | M2 |
| **M4 — Sales/Purchasing Standardization** | 3–5 days | +0.5–1 day | +1–2 days | M1 |
| **M5 — Inventory Standardization** *(incl. Item Subledger)* | 3–5 days | +0.5 day | +1 day | M1 |
| **M6 — UX Consistency + Role Management UI** | 2–3 days | +0.5 day | +1 day | M4, M5 |

### A. Business Core Acceptance (M0–M6 above)

Summing Development + Verification + Owner Acceptance, with M4/M5/M6 partly parallelizable in principle but treated sequentially here since a single Contractor is executing them one checkpoint at a time: **roughly 22–33 working days end-to-end**, spread across 6 separate Owner checkpoints, not a continuous block.

### B. Next roadmap phase beyond the Business Core

Per Section C, the immediate post-Business-Core candidates are RBAC Role Management depth, deeper Reporting/BI groundwork, and closing the cross-cutting gaps noted in Section D (audit trail, cancel/void, maker-checker) if the Owner names them as priorities at that point. **Not estimated with day-ranges here** — by design, this planning happens only once the Business Core is accepted and the Owner/Consultant have seen it running, since which of these matters most may change based on that experience.

### C. Full project completion (original blueprint scope: Manufacturing, HR, POS, E-Commerce, BI/Analytics, AI, ZATCA production certification)

**Explicitly not reliably estimable today.** Each of these is effectively its own multi-week-to-multi-month project with requirements not yet gathered at the Business-Analysis depth the completed phases (Section B, Phase 1–15 in the original blueprint) went through for the current scope. Giving a number now would be a false precision the Owner directive specifically warns against. What can be said honestly: at the current verified pace (Section A above), and assuming similar rigor is kept, a realistic order of magnitude for the full original blueprint is **several additional months, not weeks** — but this will be re-estimated properly once each module reaches its own Business-Analysis step, not guessed at now.

### Biggest uncertainty factors affecting all of the above

1. **Rework from Owner Checkpoints.** Every number above assumes the previous Milestone was approved without a major redesign request. A significant "change this" at any checkpoint extends that Milestone and pushes every later one back by the same amount.
2. **Accounting reconciliation risk (M1).** If the new reports (Income Statement, Balance Sheet, Aging) surface a discrepancy against existing Journal Entry data, that becomes a data-integrity investigation, not a UI fix — could extend M1 meaningfully. This is a real possibility precisely because M1 is the first time this data gets read back in aggregate.
3. **Demo data realism (M3).** "Realistic" bilingual data generation is inherently a judgment call on quality vs. speed — could run faster or slower than estimated depending on how much manual curation the Owner wants versus programmatic generation.
4. **Scope discovery.** Per Section 15 of the Owner directive, any Critical/High issue found mid-Milestone gets fixed within that Milestone (extending it); anything Medium/Low gets logged and deferred (not extending it) — so estimates could move in either direction depending on what's actually found, not just optimistically assumed clean.

---

## J. Risks

| Risk | Severity | Notes |
|---|---|---|
| Cancel/void workflow doesn't exist anywhere | Medium | Not currently blocking the Business Core, but will surface as soon as the Owner tries to correct a mistaken entry during demo testing. Recommend deciding at Milestone 4 checkpoint whether a minimal cancel path is now in scope. |
| Sparse audit trail | Low–Medium | Not a security issue (RLS still isolates data correctly) but limits "who did this" answers. Flagged, not yet scheduled — candidate for a later checkpoint decision. |
| No maker-checker/approval workflow | Low for now | Present in the original blueprint's ambition but not required for a working Business Core; explicitly deferred until named by the Owner. |
| Demo data script complexity | Medium | Must go through the service layer under RLS/`erp_app`, which is slower to write than raw SQL inserts but is the only approach consistent with the "no superuser bypass" rule — budgeted accordingly in Milestone 3. |
| Report screens becoming a second, disconnected "reporting module" | Medium | Mitigated by building Milestone 2's reports directly against Milestone 1's new Accounting views rather than a separate data path — this ordering is deliberate. |
| Single-agent execution pace | Informational | All estimates in Section I assume the current one-Contractor, checkpoint-gated pace; they are not reducible by "working faster" without changing the review/verification standard, which the Owner has explicitly said not to relax. |

No Critical or architectural-red-flag risks were found in this audit — nothing here requires an Owner decision before Milestone 0/1 can start.

---

## K. Next Execution Milestone

**Milestone 0 — Baseline, Governance & Business-Core Readiness** is this document plus its companions (`docs/erp-ux-standard.md`, the updated `docs/project-progress.md`, and the fresh baseline verification in Section A). Per the Owner directive's own git discipline (Section 20: commit only after a Milestone is completed **and accepted**), nothing has been committed yet — including Phase 17D (Payments), which remains implemented, tested, and re-verified but intentionally uncommitted until this checkpoint is approved. Once approved, two separate, clean commits are planned (not one mixed commit): (1) Phase 17D — Payments, unchanged from what was already reviewed and approved at the last checkpoint, and (2) Milestone 0's governance documentation. Keeping them separate matches Section 20's "don't mix unrelated changes" rule — Payments is a business feature, Milestone 0 is process documentation.

**Milestone 1a — General Ledger, Income Statement, Balance Sheet**: done, committed, Owner Acceptance environment prepared — awaiting the Owner's own test and explicit approval (not assumed from this document).

**Milestone 1b — Customer/Vendor Subledgers, AR/AP Aging, JE source-document drill-down**: implemented, tested (159/159 suite), verified, live-demonstrated — **not yet committed**, Owner Acceptance environment prepared (`docs/owner-acceptance-m1b.md`), awaiting the Owner's own test and explicit approval. Full detail, including two real findings surfaced (and one fixed) during this Milestone's own verification, in `docs/17f-subledgers-and-aging.md`.

**Candidate for what's technically unblocked next** (per Rule 0 in Section G, this is a dependency note for the Owner's decision, not a self-issued go-ahead): with M1a and M1b both done, **Milestone 2 — Reporting Polish** is the only Milestone fully unblocked by what's already shipped (it needs real Accounting views to link to, per §C2, and now has them). It is **not started**, and will not start without an explicit Owner instruction to proceed.

All Milestones follow the QA/Acceptance Strategy in Section H and the full Owner Checkpoint Protocol in Section G.

**UI/UX System-Wide Audit + Foundation Milestone (2026-08-03)**: full detail in `docs/project-progress.md`'s dated entry and `docs/18-ui-ux-audit.md`. Summary: the audit (no fixes) shipped first per the Owner's instruction, then a scoped "UI/UX Foundation + Company Context" bundle was approved and executed — four shared utilities (currency formatting, status-badge variants, company-name resolution, a toast system) applied as swaps across Dashboard/Sales/Purchasing/Inventory/Payments/Accounting, plus a real Company Context (company-selection screen, Topbar switcher) backed by two new, narrowly-scoped backend endpoints. **Implemented, Tested (165/165 backend, 13 new), Verified, Live Demonstrated** (full two-company browser walkthrough including the real Topbar switcher click and a true SPA switch with no stale data/permissions) — **Owner Accepted: pending**. Two real bugs were found and fixed during this milestone's own live verification (an RLS company-context bug in the access-grant endpoint; a hydration race that could bounce an already-logged-in user off `/select-company` on a hard reload) — neither shipped unfixed. Explicitly deferred, not started: Sales Order/Invoice list pages, Purchasing/Inventory table redesign onto `ERPListView`, Cycle Count UI, Reporting expansion, Cancel/Void, Audit Trail expansion — these remain candidates for a future Milestone, not decided here.

**UI/UX Evolution: Entity Media Foundation + Master Data Image Support
(2026-08-03)**: full detail in `docs/project-progress.md`'s dated entry.
Summary: a shared local-disk Entity Media Foundation (no new
infrastructure dependency) plus one shared `EntityImage`/
`EntityImageUpload` component pair, used identically for Company logo,
Customer/Vendor image, and Product image — not four separate builds.
Company logo now flows through Topbar/Dashboard/`/select-company`/
Accounting print statements as one unit with company switching, matching
§E item 5 (Company identity visibility pass) above — that roadmap item is
now substantially delivered for Company; Partner/Product identity images
are a new addition beyond what §E originally scoped. Customer/Vendor/
Product images wired into Master Data create/edit/detail/list via the
existing `RecordCard`/`ERPListView`/`Can` patterns (one new optional
`avatar` slot added to `RecordCard`, no new list pattern). A genuine RLS
bug in this milestone's own new upload/delete endpoints (`db.refresh()`
after `db.commit()` losing its RLS transaction context) was found by this
milestone's own tests and fixed before shipping. **Implemented, Tested
(173/173 backend, 8 new), Verified, Live Demonstrated** (real file
uploads via the real API against a freshly-bootstrapped user/company,
confirmed rendering across Topbar/Dashboard/Company Profile/Customer/
Vendor/Product list+detail, confirmed fallback and Arabic/RTL states) —
**Owner Accepted: pending**. Per the Owner's explicit instruction, Bundle
3 (§ K above, Purchasing/Inventory onto `ERPListView`) was **not**
started as part of this pass — Master Data's own UX consistency gap was
smaller than originally scoped (already largely on the shared pattern per
the audit; only empty-state copy was genuinely missing) and is now
closed.

**Product/ERP Architecture Reassessment + Settings Architecture
Foundation (2026-08-04)**: at the Owner's explicit direction, a planning-
only pass (no code) benchmarked the current system against Odoo/
ERPNext/Microsoft Dynamics 365 Business Central/SAP Business One's
official documentation, specifically to judge maturity on UX/product-
architecture terms, not feature count. Key finding: the current unified
`Partner` (customer/vendor via flags) already matches a real
international pattern (SAP Business One's Business Partner) — a full
Party/Contact/Employee merge was assessed and explicitly **not**
recommended now (no benchmarked system merges Employee in either). The
two most foundational, real gaps identified: no Settings/configuration
architecture at all (not even the company's own name was editable after
`/bootstrap`), and no way to change an already-created role's
permissions (a recurring operational blocker, hit twice in the prior
milestone). **Settings Architecture Foundation** was chosen as the
single next milestone over other real candidates (Address Book, Audit
Trail UI, a Partner "360° view" tab) specifically because it resolves
both P0 gaps at once, in one coherent, reusable shell, with the lowest
migration risk (no changes to any Sales/Purchasing/Inventory/Payments/
Accounting/Master Data table).

Delivered: a reusable `SettingsShell` (section nav + content area,
extensible to Sales/Purchasing/Inventory/Accounting/Payments/System
settings later without redesign); `/settings/company` (the first
endpoint able to edit `legal_name`/`legal_name_ar`/`vat_number`/
`cr_number` at all, deliberately excluding `base_currency`/
`valuation_method`/`zatca_environment` for correctness reasons,
documented not silent); `/settings/security` (list/create roles, edit
any role's full permission set via a checkbox matrix — the actual fix
for the "no way to add a permission to an existing role" gap first
documented in Milestone 1b and hit again in the Entity Media Foundation
milestone). A genuine RLS-related bug (a VAT-uniqueness pre-check that
RLS made unreliable across companies) was found by this milestone's own
new test and fixed via the correct pattern (catch the database's own
unique-constraint violation) rather than trusting a cross-company
SELECT. **Implemented, Tested (183/183 backend, 10 new), Verified, Live
Demonstrated** (grant/revoke of a permission on an already-existing
role, confirmed to take effect immediately with no logout; Arabic/RTL
and mobile-responsive behavior confirmed) — **Owner Accepted: pending**.
Explicitly deferred, not started: Company/Module settings beyond the
Company section shipped here, Address Book (multi-address/multi-contact
on Partner), Audit Trail UI (backend infrastructure already exists,
barely wired), Attachments/Documents, Bundle 3 — these remain candidates
for future milestones, not decided here.

**Bundle 3 — Purchasing/Inventory List & Form Consistency (2026-08-04,
same day, Owner-approved scope)**: full detail in
`docs/project-progress.md`'s dated entry. Summary: Purchasing's two tabs
and Inventory's four tabs moved from a hand-rolled `<Table>` (no search/
sort/pagination/permission-gating, per `docs/18-ui-ux-audit.md` finding
A1) onto the same `ERPListView` every other list screen already uses —
frontend-only, no backend or database change. A genuine "buried
information" gap (Purchasing lists never showed the vendor name, only
implicitly) was fixed along the way by reusing the exact resolver pattern
Inventory already had for products. The three inline quick-create forms
in Inventory deliberately stayed inline (not `FormView` pages) to avoid
adding clicks, but gained the same `<Can>` gating every mutating action
elsewhere in the app already has. **Implemented, Tested (183/183 backend
— unchanged, confirmed no backend file touched), Verified, Live
Demonstrated**: a complete real flow (Purchase Order → Confirm → Goods
Receipt → Vendor Bill → Approve → Stock → Transfer) end to end with
correct numbers at every step, plus a second pass as a genuinely
permission-limited user confirming gated actions are absent (not
disabled) and the backend independently still returns 403 — **Owner
Accepted: pending**. Per the Owner's explicit instruction, no other
Bundle or milestone was started in this pass.

---

## Global Roadmap Status

Evidence basis: direct repository inspection (modules, migrations, tests, frontend screens), the two-agent module-capability audit performed for `docs/project-progress.md`, and the Phase 17D re-audit. Percentages marked "(est.)" are judgment calls where no clean automated metric exists (e.g., "how much of a design system is done"); all others are counted from concrete evidence (endpoints, screens, passing tests).

| Area | Status | Completion | Notes |
|---|---|---|---|
| Foundation / Architecture | 🟢 Strong | 90% | Modular monolith, one-way module dependencies, Docker, CI baseline all in place and stable across 7 completed phases. |
| Security / RLS | 🟢 Complete | 100% | Verified: 3-tier DB roles, `FORCE ROW LEVEL SECURITY` on every business table, 24/24 RLS tests, no superuser in the runtime path. |
| Identity / Users / RBAC | 🟢 Strong | 85% | Login, 2FA, roles/permissions enforced; Role Management UI now shipped (Settings Architecture Foundation) — roles can be created and their permissions edited live via `/settings/security`, closing the former "permissions only editable via seed data" gap; still missing per-user permission overrides and field-level permission UI (schema supports it, unused). |
| Master Data | 🟢 Strong | 88% | Products, Categories, UOM, Customers/Vendors fully on the design system with CRUD + validation. |
| Sales | 🟡 Partial | 55% | Full Quotation→Payment lifecycle works end-to-end; missing statement/history/report screens (Section D). |
| Purchasing | 🟡 Partial | 58% | Mirrors Sales — PO→Payment lifecycle works; list screens now on `ERPListView` with real permission gating (Bundle 3); same statement/report gap remains. |
| Inventory | 🟡 Partial | 58% | Warehouses/stock/transfers/cycle counts work and post correctly; list screens now on `ERPListView` with real permission gating (Bundle 3); missing valuation/low-stock/history reports. |
| Accounting | 🟢 Strong (pending commit) | 85% | CoA, Journal Entries, Trial Balance, correct auto-posting from every module, General Ledger, Income Statement, Balance Sheet (M1a), plus **Customer/Vendor Subledgers, AR/AP Aging, JE source-document drill-down (Milestone 1b — new, live-verified)**; missing period-closing and Vendor Bill's own detail page (Subledger row not clickable). |
| Payments | 🟢 Strong (pending commit) | 85% | Full customer/vendor payment lifecycle, real allocation with concurrency protection, live-verified; refund/credit-application flow deliberately deferred. |
| Reports | 🔴 Minimal | 15% | A handful of flat CSV exports; no interactive filters, no drill-down yet. |
| ZATCA (e-invoicing) | 🟡 Partial | 40% | Sandbox integration works for simplified/standard invoices; production certification not yet pursued (explicitly out of scope until named). |
| Manufacturing | ⚪ Not started | 0% | Out of scope for the current Business Core per Owner directive. |
| HR | ⚪ Not started | 0% | Out of scope for now. |
| Projects / Construction | ⚪ Not started | 0% | Out of scope for now. |
| POS | ⚪ Not started | 0% | Out of scope for now. |
| E-Commerce | ⚪ Not started | 0% | Out of scope for now. |
| BI / Analytics | ⚪ Not started | 0% | Out of scope for now; depends on Reports (above) maturing first. |
| AI features | ⚪ Not started | 0% | Out of scope for now. |
| UX / UI Design System | 🟡 Partial (est.) | 75% | Phase 17A/17B established shared list/form/table components and i18n+RTL; Company Context + Entity Media Foundation (logos/images for Company/Customer/Vendor/Product) now shipped; Purchasing/Inventory list-consistency pass (Bundle 3) still needed (Section E). |
| Testing / QA | 🟡 Good, uneven coverage | 65% (est.) | ~141 backend tests, strong on Payments/Sales/RLS; Reports and several UI paths have little to no automated coverage. |
| Deployment / DevOps | 🟢 Strong | 95% | Docker Compose, role bootstrap, migration discipline, health checks all working and repeatedly verified across phases. |

---

## What This Plan Does Not Do

Per the Owner's explicit instruction, this document contains **no code changes** and starts **no implementation**. It is a planning and audit artifact only, consistent with (and cross-referenced to) `docs/project-progress.md` and `docs/erp-ux-standard.md`, which together remain the live source of truth for day-to-day status.

**Milestone 0 is now complete on the Contractor side. Waiting for Owner/Consultant approval before any commit is made or Milestone 1 begins.**
