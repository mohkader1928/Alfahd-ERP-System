# MASTER EXECUTION PLAN

**Prepared by:** Contractor (Claude Code) — for Owner review, with Consultant (ChatGPT) available for a second opinion on any architectural point below.
**Date:** 2026-08-02 (updated same day under the "MASTER EXECUTION DIRECTIVE — Milestone 0" governance instruction)
**Trigger:** Owner directive "PROJECT EXECUTION DIRECTIVE — OWNER / CONSULTANT / CONTRACTOR MODE," followed by "MASTER EXECUTION DIRECTIVE — Milestone 0: Baseline, Governance & Business-Core Readiness."
**Status:** Milestone 0 deliverable. No application code was written to produce this — only documentation and a fresh, real verification pass (Section A). Waiting for Owner approval before Milestone 1 (or any code) begins.

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
| **M1 — Accounting Standardization** | Payments (M0) committed; Journal Entry posting already correct | Income Statement, Balance Sheet, AR/AP Aging, GL drill-down, Customer/Vendor statements | Scenario #7 in Section D2 passes live | 4–7 days | Report logic must reconcile exactly with existing JE data — any discrepancy is a data-integrity bug, not a UI bug, and must stop the Milestone |
| **M2 — Reporting Polish** | M1 (reports need real Accounting views to link to) | Filterable Sales/Purchasing/Inventory report screens wired to real data | Owner can filter by date/customer/status and get correct results | 3–5 days | Risk of becoming a second, disconnected reporting path if not built against M1's views (see Section J) |
| **M3 — Demo Data Mechanism** | M2 (so reports have data worth seeding) | Idempotent seed script, ~100 records/type, transactional spread (Section F) | Script reruns cleanly; Owner sees a populated system end to end | 2–3 days | Must go through service layer under RLS — slower than raw SQL, non-negotiable per Owner directive |
| **M4 — Sales/Purchasing Standardization** | M1 (statements need Accounting views) | Customer/Vendor statement screens, history views, cancel-workflow decision | Statements match Accounting's own AR/AP figures exactly | 3–5 days | Cancel/void is a real scope decision, not just UI — must be explicitly scoped at this Milestone's checkpoint, not assumed |
| **M5 — Inventory Standardization** | M1 (valuation ties to Accounting) | Stock valuation report, low-stock view, movement history | Valuation report reconciles with Accounting's Inventory account balance | 2–4 days | Valuation method consistency (the system already supports a configured method — must not introduce a second one) |
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

## E. UX Roadmap (parallel workstream, not blocking Business Core work)

Runs alongside the Business Core work, one small pass per checkpoint rather than a big separate phase:

1. **Design language audit** — catalogue every list/form/table/filter/select/badge/dialog pattern currently in use across Sales, Purchasing, Inventory, Master Data, Payments; identify the 1–2 modules that drifted from the Phase 17A design system (Payments' new picker introduced a dependent-select pattern worth reusing elsewhere).
2. **Speed-of-entry pass** on the highest-traffic forms first: Customer/Vendor create, Sales Order, Purchase Order, Invoice, Payment — smart defaults (today's date, last-used warehouse/account), searchable selects everywhere an ID is picked, fewer required clicks.
3. **Consistency pass** on status badges, empty states, loading states, and error messages — currently inconsistent module-to-module.
4. **Reusable components** promoted from what Payments already built (the balance-aware dependent picker) into the shared component library so future modules don't reinvent it.

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

### The cycle

**EXECUTE → VERIFY → STOP → REPORT → OWNER ACCEPTANCE → CONTINUE**

- **EXECUTE**: build the Milestone's scope, and only that scope.
- **VERIFY**: run the QA/Acceptance Strategy (Section H) — tests, lint, type checks, build, a live browser walkthrough of the real business scenario, Docker health, migration head.
- **STOP**: work halts. No new Milestone starts. No further scope is added, even if a natural next step is obvious.
- **REPORT**: deliver the checkpoint report (template below) in the chat, in the Owner's language, with technical terms briefly explained on first use.
- **OWNER ACCEPTANCE**: the Owner (with the Consultant's input if wanted) reviews and explicitly approves, requests changes, or rejects.
- **CONTINUE**: only after explicit approval does the next Milestone's EXECUTE step begin.

There is no path from EXECUTE directly to CONTINUE. A Milestone that "looks done" is not a Milestone that has been accepted.

### Checkpoint report template (required structure, every time)

**A. What was completed** — concretely, not "Payments module done" but the specific capabilities delivered.
**B. What remains** — for this Milestone specifically, if anything was descoped or deferred within it.
**C. Evidence** — test counts and results, specific endpoints, specific files, migration IDs; screenshots/live-verification narrative where the Milestone touched the UI.
**D. Business scenarios** — the specific things the Owner can now do that they could not do before this Milestone.
**E. UI walkthrough** — literal click-by-click steps to try B and D from a browser, no SQL required.
**F. Regression status** — explicit confirmation that Phase 17A/17B/17C-RLS/17D and prior Milestones still pass their own tests; anything that changed in shared code gets called out by name.
**G. Roadmap status** — where this leaves the Global Roadmap Status table and the Timeline (Section I) — did anything get faster or slower than planned, and why.
**H. Risks / limitations** — everything known and not yet resolved, honestly, even if minor.
**I. Next step** — the specific next Milestone, and the one-sentence reason it's next rather than something else.

### A rule about language in these reports

"Verified" is only used when verification actually happened this checkpoint. Every report distinguishes, explicitly, between: **Implemented** (code exists) → **Tested** (automated tests pass) → **Verified** (manually/independently re-checked, e.g. re-querying an endpoint after a UI action) → **Live demonstrated** (walked through in a real browser session) → **Owner accepted** (the Owner has actually said yes). These are not interchangeable, and a report will say which of these applies to each claim rather than using "done" as a catch-all.

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
| **M1 — Accounting Standardization** | 4–7 days | +0.5–1 day | +1–2 days (Owner runs Scenario #7) | M0 |
| **M2 — Reporting Polish** | 3–5 days | +0.5–1 day | +1–2 days | M1 |
| **M3 — Demo Data Mechanism** | 2–3 days | +0.5 day | +1 day (Owner test-drives populated system) | M2 |
| **M4 — Sales/Purchasing Standardization** | 3–5 days | +0.5–1 day | +1–2 days | M1 |
| **M5 — Inventory Standardization** | 2–4 days | +0.5 day | +1 day | M1 |
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

**Milestone 1 — Accounting Standardization** (the recommended next body of work): Income Statement, Balance Sheet, AR/AP Aging, General Ledger account drill-down, and Customer/Vendor statement screens — built on top of the Journal Entry data that Sales, Purchasing, and Payments already post correctly today. This is recommended over any other candidate because it (a) requires no new module dependency — the data already exists and is already correct, (b) closes the single largest gap identified in Section D, and (c) directly unblocks Milestone 2 (Reporting Polish) and Milestone 4 (Sales/Purchasing statements), which both need these Accounting views to build on rather than inventing their own.

Both milestones follow the QA/Acceptance Strategy in Section H and the full Owner Checkpoint Protocol in Section G — Milestone 1 does not begin until this Milestone 0 report is explicitly approved.

---

## Global Roadmap Status

Evidence basis: direct repository inspection (modules, migrations, tests, frontend screens), the two-agent module-capability audit performed for `docs/project-progress.md`, and the Phase 17D re-audit. Percentages marked "(est.)" are judgment calls where no clean automated metric exists (e.g., "how much of a design system is done"); all others are counted from concrete evidence (endpoints, screens, passing tests).

| Area | Status | Completion | Notes |
|---|---|---|---|
| Foundation / Architecture | 🟢 Strong | 90% | Modular monolith, one-way module dependencies, Docker, CI baseline all in place and stable across 7 completed phases. |
| Security / RLS | 🟢 Complete | 100% | Verified: 3-tier DB roles, `FORCE ROW LEVEL SECURITY` on every business table, 24/24 RLS tests, no superuser in the runtime path. |
| Identity / Users / RBAC | 🟡 Partial | 75% | Login, 2FA, roles/permissions enforced; missing a Role Management UI (permissions are only editable via seed data today). |
| Master Data | 🟢 Strong | 88% | Products, Categories, UOM, Customers/Vendors fully on the design system with CRUD + validation. |
| Sales | 🟡 Partial | 55% | Full Quotation→Payment lifecycle works end-to-end; missing statement/history/report screens (Section D). |
| Purchasing | 🟡 Partial | 55% | Mirrors Sales — PO→Payment lifecycle works; same statement/report gap. |
| Inventory | 🟡 Partial | 55% | Warehouses/stock/transfers/cycle counts work and post correctly; missing valuation/low-stock/history reports. |
| Accounting | 🟡 Partial | 55% | CoA, Journal Entries, Trial Balance, and correct auto-posting from every module all work; missing Income Statement, Balance Sheet, Aging, GL drill-down — **Milestone 1**. |
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
| UX / UI Design System | 🟡 Partial (est.) | 70% | Phase 17A/17B established shared list/form/table components and i18n+RTL; consistency pass still needed (Section E). |
| Testing / QA | 🟡 Good, uneven coverage | 65% (est.) | ~141 backend tests, strong on Payments/Sales/RLS; Reports and several UI paths have little to no automated coverage. |
| Deployment / DevOps | 🟢 Strong | 95% | Docker Compose, role bootstrap, migration discipline, health checks all working and repeatedly verified across phases. |

---

## What This Plan Does Not Do

Per the Owner's explicit instruction, this document contains **no code changes** and starts **no implementation**. It is a planning and audit artifact only, consistent with (and cross-referenced to) `docs/project-progress.md` and `docs/erp-ux-standard.md`, which together remain the live source of truth for day-to-day status.

**Milestone 0 is now complete on the Contractor side. Waiting for Owner/Consultant approval before any commit is made or Milestone 1 begins.**
