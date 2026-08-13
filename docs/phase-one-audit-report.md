# Phase-One Product Audit — ERP System Sellability Review

**Purpose**: an honest, evidence-based answer to "is this ERP Phase-One complete and
sellable, and if not, what exactly is left." This is an audit, not a plan — nothing in
this document was implemented as part of writing it.

**Method**: source-of-truth docs (`README.md`, `docs/project-progress.md`,
`docs/master-execution-plan.md`, `docs/02-functional-requirements.md`,
`docs/11-testing.md`, module design docs) read directly; every completion claim below
verified against current source code, migrations, and tests — not against
`docs/project-progress.md`'s structured "Completion Matrix," which is confirmed stale
(written after Milestone 1b, before roughly 60 subsequent commits: the 3-Day Brief
P0-1 through P0-9, Fixed Assets, RBAC completion, JE-visibility/editing, partial
invoicing, and the search-select feature). Seven parallel research passes (one per
module/domain) independently re-verified current state against source; their evidence
is cited throughout by file:line, migration filename, or test name.

**Status**: All 7 module/domain audits complete (Accounting, Sales, Purchasing,
Inventory, Fixed Assets, Security/RBAC, Reporting/Dashboard/UX). Full backend
regression suite ran to completion: **391 passed, 1 failed** (44 test files, real
dockerized Postgres, `1000.21s`). The one failure is not incidental — it's a genuine,
previously-undiagnosed concurrency bug this audit's own run surfaced live; see §4.4
item 2 for the exact root cause captured from the failure's stack trace.

---

## 1. Executive Summary

The core transactional engine of this ERP is **real, GL-integrated, and
concurrency-hardened** — genuinely further along than the project's own documentation
suggests, because `docs/project-progress.md`'s structured Completion Matrix is stale by
roughly 60 commits. Purchase-to-Pay and Order-to-Cash both trace end-to-end through real
service calls with tests proving each link (§5). Fixed Asset acquisition-through-
disposal is the single most rigorously GL-reconciled flow in the system, proven equal to
Trial Balance by direct test assertion, not construction alone. The RBAC/RLS
multi-tenancy core (76 permissions, 61 `FORCE ROW LEVEL SECURITY` statements) shows zero
detected cross-tenant leakage in either this audit or its own extensive test suite.

That said, **six P0 gaps block a "Phase-One Complete / Sellable" declaration**, and
none of them are about a module being unbuilt — they're about a control existing in
name but not being real (or, in one case, a race condition this audit's own regression
run caught live):

1. **VAT is hardcoded to 15% everywhere** (backend ignores the `tax_rate_id` it stores;
   frontend's rate picker is bound to a non-functional placeholder UUID, duplicated
   across 8 files) — found independently by both the Accounting and Sales audits.
2. **Fiscal-period closing has zero frontend UI and zero tests** — the backend enforces
   it correctly, but no user can ever actually close a period through the product; this
   entire control is currently dormant.
3. **2FA cannot be enabled by a user** — verification logic is real and tested, but no
   enrollment endpoint exists anywhere; `is_2fa_enabled` can only be set by direct
   database manipulation.
4. **No password reset, no login lockout** — baseline commercial-product hygiene,
   entirely absent.
5. **Audit-trail coverage stops at roughly half the system** — Sales invoicing/credit
   notes, all of Inventory, all of Fixed Assets, and Payments have zero audit-log
   entries, while Accounting/Identity/parts of Purchasing do.
6. **A real, reproducible concurrency bug in first-time stock receipt** — this audit's
   full regression run (391 passed, 1 failed) caught `get_or_create_for_update`
   double-inserting under concurrent load, previously misattributed to "flaky test
   infrastructure" in the project's own notes. Root cause identified precisely (§4.4
   item 2), fix is small and well-precedented (the project already used the identical
   `ON CONFLICT` fix for an unrelated race in the admin-role permission sync).

A seventh item is operational rather than code-level but serious: **116 commits exist
only on this machine** — `origin/main` has not been updated since the very first commit.

None of these gaps require rebuilding anything. Each is a bounded, well-understood
addition to code that already exists and already works correctly around it — which is
exactly why a focused closure pass (§10) is realistic rather than a re-architecture.

---

## 2. Original Business Objective (source of truth)

Reconstructed from `README.md`, `docs/02-functional-requirements.md`, and
`docs/17-erp-standardization-master-blueprint.md`: a modular-monolith **core ERP
nucleus** for the Saudi market — Accounting, Sales (with ZATCA e-invoicing), Inventory,
Purchasing, and Reporting, explicitly scoped to defer CRM/POS/Manufacturing/HR/
Construction/AI/E-commerce/BI to a backlog. Since the nucleus was declared "functional,
not production-hardened" in the README, the project ran a "3-Day Brief" of 8 P0 items
(all completed — see §3) plus an owner-requested 9th (Sales/Purchase Returns), and then
continued well beyond that brief: Fixed Assets (not in the original nucleus scope —
added as P0-5), full RBAC completion, Chart of Accounts hierarchy, dashboard/UX passes,
and the search-select UX feature. Fixed Assets is therefore a **genuine scope addition**
beyond the original blueprint, now itself a first-class module under audit.

---

## 3. Ground Truth: What's Actually Been Built (independent of any prior doc's claims)

- **117 local commits**, all on `main`. **`origin/main` is 116 commits behind** — the
  GitHub remote has not been updated since the very first commit (`a08586d`). This is a
  real operational/backup risk, not a documentation nitpick: this machine is currently
  the single point of failure for the entire project history.
- **45 migrations**, single head (`b6c7d8e9f0a1`), DB confirmed at head — no migration
  branching, no drift.
- **44 backend test files**; **11 backend modules** (identity, accounting, sales, zatca,
  inventory, purchasing, reporting, payments, fixed_assets, attachments, notifications).
- **59 frontend routes** (`page.tsx` files).
- **Zero `TODO`/`FIXME`/`XXX`/`HACK`** markers anywhere in `backend/src` or
  `frontend/app`/`features`/`components` — this codebase's convention is to document
  known gaps in `docs/project-progress.md`'s narrative log, not in-code comments. This
  makes the *doc* the only place gaps are self-admitted, which is exactly why it
  matters that the structured matrix in that doc is stale (the narrative log at the top
  is current; the matrix in the middle is not).
- `ruff check src tests` — **clean**.
- `.env*` secret files correctly gitignored, never committed.
- **No CI pipeline** (no `.github/workflows`) — tests/lint are documented and runnable,
  not automated on push.
- **No backup/recovery section** in `docs/14-deployment.md` — deployment doc covers
  containerized topology only.
- The original "3-Day Brief" (8 P0 items, `docs/project-progress.md` narrative) is
  **fully committed**: P0-1 (PO short-close) → P0-8 (Dashboard KPIs), plus P0-9
  (Sales/Purchase Returns, owner-requested addition). All of it happened *before* this
  audit was requested — the user's "three-day intensive closure period" reference is to
  a plan that already executed, not one still pending.

---

## 4. Module-by-Module Audit

Classification legend: **A**=COMPLETE · **B**=COMPLETE BUT NEEDS HARDENING ·
**C**=PARTIALLY COMPLETE · **D**=IMPLEMENTED BUT INTEGRATION GAP ·
**E**=IMPLEMENTED BUT DOCUMENTATION GAP · **F**=MISSING · **G**=OUT OF SCOPE

### 4.1 Accounting / General Ledger / Fixed Assets

| # | Capability | Class | Risk | Evidence |
|---|---|---|---|---|
| 1 | Chart of Accounts (4-level hierarchy, posting restrictions, cycle detection) | A | P2 | `services.py:210-335`; migration `f2a3b4c5d6e7`; `test_chart_of_accounts_hierarchy.py` (11 tests) |
| 2 | Journal Entry lifecycle (draft/post/reverse, balance enforcement) | C | **P1** | `services.py:371-511`; **no edit/delete on a draft JE exists at all** — a mistaken draft is unrecoverable via the product |
| 3 | Fiscal periods (open/close, enforcement) | D | **P0** | Backend enforces closed periods (`PeriodClosedError`, `services.py:449-451`) but **zero frontend UI** (`grep` for `fiscal-period` across `frontend/` = no matches) and **zero test coverage** — dead functionality a buyer could be misled by |
| 4 | Financial reports (TB/GL/IS/BS) + detail-level rollup | A | P2 | `services.py:514-777,729-776`; `test_report_detail_level_rollup.py` proves totals invariant across rollup levels — a real, tested invariant |
| 5 | Customer/Vendor Subledgers + AR/AP Aging, reconciled to GL | A | P2 | `payments/application/services.py:209-354`; `test_payments_subledger_m1b_smoke.py:483-487` directly asserts subledger sum == GL closing balance |
| 6 | Payments → GL integration, concurrency-safe allocation | A | P2 | `payments/application/services.py:47-206`; `test_payments_m6_smoke.py:379-403` (concurrent-overallocation race test) |
| 7 | Fixed Assets → GL integration + reconciliation report | A | P2 | `fixed_assets/application/services.py:285-384`; `test_fixed_assets.py:394-496` — reconciliation report uses the *same* GL balance function as Trial Balance, proven equal by test |
| 8 | VAT / Tax computation | F | **P0** | `sales/services.py:419,719`, `purchasing/services.py:561,664,907` all hardcode `Decimal("15.00")`; frontend duplicates a non-functional placeholder tax-rate UUID across 8 files; a real `TaxRate` table exists and is seeded but is never actually looked up |
| 9 | Audit trail on accounting/period actions | C | P1 | 6 call sites in `accounting/api/routes.py`; fiscal period close itself is **not** audited despite being as sensitive as JE posting |
| 10 | Multi-currency | F | P1/P2* | No currency field anywhere in JE/Account models; single `Company.base_currency_id` only. *P1 if any pipeline customer needs FX, P2 if confirmed SAR-only market |
| 11 | Fixed Asset register/categories/depreciation/disposal | A/C | mixed | See detail below |
| 12 | Fixed Asset categories carrying GL accounts | C | **P1** | `FixedAssetCategory` model has no asset/accum-depreciation/expense account columns — each asset's 3 GL accounts are picked freely per-asset with no category-level default or enforcement, so two same-category assets can silently post to different accounts |
| 13 | Fixed Asset acquisition link to Purchasing | D | P1 | Acquisition posts a real JE but is **entirely standalone** — no PO/Vendor Bill → Asset link exists; every capex purchase requires duplicate manual entry |
| 14 | Fixed Asset depreciation (straight-line, idempotent, category-scoped) | A | P2 | `services.py:425-509`; DB `UNIQUE(fixed_asset_id, period_month)` + explicit check, both tested |
| 15 | Fixed Asset disposal (gain/loss, concurrency-safe) | A | P2 | `services.py:511-563`; both gain and loss paths TB-cross-checked in tests |
| 16 | Fixed Asset permission-denial test coverage | B | P1 | `require_permission()` correctly wired on every route, but **no test asserts a 403** for any Fixed Assets action |

**Accounting/Fixed Assets top findings**: the GL-posting core (Payments, Fixed Assets,
reports) is the most rigorously reconciled part of the entire system — reconciliation
isn't just claimed, it's proven by tests that compare against the same balance function
Trial Balance uses. But VAT not being real and fiscal periods being unreachable are two
genuine P0s that undercut "sellable to a VAT-registered Saudi business" specifically.

### 4.2 Sales

| # | Capability | Class | Risk | Evidence |
|---|---|---|---|---|
| 1 | Quotation → Order → partial Invoice lifecycle | A | P2 | `services.py` (partial invoicing via `qty_invoiced`, migration `c4d5e6f7a8b9`); `test_sales_zatca_m2_smoke.py:587-738` |
| 2 | ZATCA e-invoicing (hash chain, QR, B2B/B2C routing) | D | **P0*** | Hash chaining/routing structurally real and tested; but `sandbox_gateway.py` and `signing.py` both explicitly self-document "NOT A REAL ZATCA INTEGRATION" / "NOT_ZATCA_COMPLIANT". *P0 only if going live in KSA is a Phase-One requirement — otherwise a scoped, documented exclusion |
| 3 | VAT rate (see §4.1 item 8 — cross-module finding) | F | **P0** | Same hardcoded-15% issue, confirmed independently from the Sales side |
| 4 | Credit Notes / Sales Returns (restock + reversing JE + idempotency) | A | P2 | `services.py:572-1037`; `test_credit_note_idempotency.py` (concurrent-replay test) |
| 5 | Customer payments/receipts, statement | A | P2 | Shared with Payments module — see §4.1 item 6 |
| 6 | Cancel support | C | P1 | Sales Order cancel is real and tested; **Quotation and Invoice both model a `cancelled` status with zero code path to ever reach it** |
| 7 | Audit trail | F | P1 | Zero `AuditLogRepository` calls anywhere in `sales` module |
| 8 | Document numbering & concurrency (ICV races, duplicate-invoice prevention) | A | P2 | Dedicated fix lineage (`3d5c913`, `eab2f10`, `ccac510`); `test_zatca_icv_concurrency.py`, `test_invoice_duplicate_prevention.py` |
| 9 | Frontend coverage (list pages, permission-gated actions) | A | P2 | `sales/orders/page.tsx`, `sales/invoices/page.tsx` both exist with pagination; workflow buttons gated on status **and** permission — supersedes the stale doc's claim otherwise |
| 10 | Reports (by-customer/product/period, statement, export) | A | P2 | `test_sales_reporting_bundle_e.py`; By-Customer includes payment/balance columns |

**Sales top finding**: the core loop is real, tested, and race-hardened — the stale
matrix's claims of "no payments," "no list pages," "dead `qty_invoiced`" are all
demonstrably false today. ZATCA production-certification and the shared VAT gap are the
real blockers, not the sales workflow itself.

### 4.3 Purchasing

| # | Capability | Class | Risk | Evidence |
|---|---|---|---|---|
| 1 | PO lifecycle + real threshold-based approval workflow | A | P2 | `services.py:179-282`; frontend `<Can>`-gated |
| 2 | Partial receipt / data-driven short-close | A | P2 | `test_purchase_order_short_close.py` — the best-tested workflow in the module |
| 3 | 3-way match (qty/price, human-readable mismatches) | A | P1* | `domain/entities.py:29-52`; *0% price tolerance by default — any rounding difference blocks posting with a 409, a go-live friction point rather than a bug |
| 4 | Vendor Debit Note (restock, reversing JE, idempotency incl. concurrency race) | A | P2 | `test_vendor_debit_note.py`, `test_vendor_debit_note_idempotency.py` |
| 5 | Auto-billing on receipt | A | P2 | `GoodsReceiptService.record_receipt` always bills at PO price on receipt — "clean 3-way match by construction" |
| 6 | Vendor payments + AP aging reconciled to GL | A | P2 | Shared with Payments/Accounting — `test_purchases_by_supplier_report.py` reconciles AP balance against Trial Balance |
| 7 | Cancel support | F | P1 | No `:cancel` endpoint exists for PO despite `cancelled` being a modeled status |
| 8 | Audit trail | C | P1 | Only 2 call sites (short-close, reopen) — PO confirm/approve, bill approval, and debit notes are unaudited |
| 9 | Reports (Purchases by Supplier) | A | P2 | `test_purchases_by_supplier_report.py` |
| 10 | Frontend coverage (Vendor Bill detail, permission gating) | B | P2 | 12 gated actions verified by grep; no standalone "new Vendor Bill" page outside PO flow (deliberate — no bill-without-PO support) |

**Purchasing top finding**: this is the strongest-audited module against its own stale
doc — auto-confirm-every-PO, zero vendor payments, ungated buttons are all fixed. The
one clear functional gap is the missing PO cancel endpoint (cheap to add, same shape as
the already-built short-close).

### 4.4 Inventory

| # | Capability | Class | Risk | Evidence |
|---|---|---|---|---|
| 1 | Valuation (FIFO + moving-average, both real, company-selectable) | A | P2 | `domain/valuation/{fifo,average}.py`; `test_inventory_valuation.py` |
| 2 | Concurrency (row-locked stock updates) | **C** | **P0** | **Root-caused by this audit's own regression run** (391 passed, 1 failed — `test_concurrent_receipts_do_not_lose_an_update`, `UniqueViolationError` on `ux_stock_quant_product_location`). Not flaky test infrastructure: `get_or_create_for_update` (`repositories.py:106-115`) takes `SELECT ... FOR UPDATE` on an *existing* row, but a lock cannot be held on a row that doesn't exist yet — two concurrent first-time receipts for the same product+location both see "no row," both call `_create`, and the second's `INSERT` collides with the unique constraint. The code's own comment (lines 110-114) reasons this is safe ("a fresh row has no concurrent writer to race with yet"), but that reasoning doesn't hold under Postgres row-lock semantics — this is a genuine, reproducible TOCTOU race, not noise |
| 3 | Purchase receipt → stock increase (PO/GR link) | A | P2 | `purchasing/services.py:416-428` calls `inventory_service.receive_stock` directly |
| 4 | Sales issue → stock decrease → COGS journal entry | A | P1* | `sales/services.py:543-565`; *silently skips the JE line if unit cost is `0`, worth a sanity check for zero-cost receipts |
| 5 | Low stock / reorder-point alerts | A | P2 | `test_low_stock_alerts.py` — notification fires exactly once at threshold crossing |
| 6 | Cycle counts (backend + frontend, netted journal entry) | A | P2 | Contradicts an older doc's "zero frontend UI" claim — full UI exists (`cycle-counts/new`, `cycle-counts/[id]`) |
| 7 | Stock card / Cardex | A | P2 | `product_cardex` with PDF/Excel export; frontend at `stock-card/[productId]` |
| 8 | Inventory Valuation report | A | P2 | `test_inventory_valuation.py` explicitly checks FIFO reads `StockLayer` not `moving_avg_cost` — a real correctness test, not a smoke test |
| 9 | Warehouse-to-warehouse transfers | B | P2 | Real and working; no dedicated test file (rides on `issue_stock`/`receive_stock` unit coverage) |
| 10 | Manual stock receipt (`/stock/receive`) | D | P1 | Permission-gated now, but **no reason/reference field** — any authorized user can inject stock at an arbitrary cost with zero justification captured, directly distorting valuation/COGS |
| 11 | Serial/lot tracking | G | P2 | Confirmed absent, confirmed intentional (out of scope) — should be explicitly documented as a Phase-One exclusion, not discovered by a customer |
| 12 | Audit trail | F | P1 | Zero `AuditLogRepository` calls despite this module moving financial value directly |

**Inventory top finding**: functionally closer to done than the stale matrix suggests
(low-stock alerts, valuation report, cycle-count UI, stock card are all real). But this
audit's own full regression run caught a real, reproducible concurrency bug in the
first-receipt path (item 2) — previously dismissed in `project-progress.md` as "known
flaky, passes in isolation," it is not flaky, it's a genuine race with an exact fix
(swap the check-then-insert for `INSERT ... ON CONFLICT (product_id, location_id) DO
UPDATE` or a retry-on-`IntegrityError` wrapper, the same pattern this project already
used to fix the admin-role permission sync race). That, plus `/stock/receive`'s missing
reason field, are the two items worth resolving before calling this module sellable.

### 4.5 Security / Identity / RBAC / Audit

| # | Capability | Class | Risk | Evidence |
|---|---|---|---|---|
| 1 | Authentication (JWT, TOTP 2FA, password policy) | C | **P0** | TOTP *verification* is real and tested, but **no enrollment endpoint exists anywhere** — `is_2fa_enabled` can only be set by direct DB manipulation, not through the product. No account lockout, no password-reset flow |
| 2 | RBAC permission catalog | A | P2 | 76 granular permissions (`PERMISSION_CATALOG`, `seed.py:28-130`) |
| 3 | Role management (CRUD, system-role immutability) | A | P2 | `test_settings_roles.py` — system roles protected, live permission grant/revoke takes effect without re-login |
| 4 | Admin-role permission auto-sync (this session's fix) | A | P2 | Additive RLS policy + atomic `ON CONFLICT` insert; `test_admin_role_permission_sync.py` proves both the fix and non-leakage |
| 5 | Backend authorization enforcement | A | P2 | Spot-checked 7 mutating routes across 5 modules — all genuinely `require_permission()`-guarded server-side |
| 6 | Frontend permission enforcement (`<Can>`) | B | P1 | Both spot-checked detail pages gate on status **and** permission together (contradicts an older doc's status-only claim on those two pages); full sweep across all detail pages not yet done |
| 7 | Company/branch access control | B | P2 | `user_company_access` RLS + JWT-baked `authorized_companies`, re-validated every request; revoking access mid-session takes up to 30 min (token lifetime) to take effect |
| 8 | RLS coverage | A | P1** | 61 `FORCE ROW LEVEL SECURITY` statements, no orphaned gaps found; the old `role_permission`/`user_role` gap is fixed (migration `d1e2f3a4b5c6`, tested). **Residual P1: no CI check exists to keep this true for future tables |
| 9 | Audit trail (system-wide) | C | **P0** | Only 16 total call sites, concentrated in accounting (6) and identity (8); **zero in sales, inventory, fixed_assets, payments, zatca, or reporting** — the highest-value financial/inventory-moving actions are unaudited |
| 10 | Session/token handling | C | P1 | Refresh tokens are minted at login but **no endpoint ever consumes them** — dead half-feature; no logout/revocation mechanism exists; a compromised access token is valid for its full 30-minute window with no kill switch |

**Security top finding**: the RBAC/RLS/multi-tenancy core is the strongest, most
rigorously tested part of the entire system (76 permissions, 61 FORCE RLS statements,
zero detected leakage). But the *account-lifecycle* hygiene around it — 2FA enrollment,
password reset, lockout, session revocation — is either unreachable or absent, which is
a real gap for a commercial product, independent of how solid the underlying RLS/RBAC
engine is.

### 4.6 Reporting / Dashboard / UX

| # | Capability | Class | Risk | Evidence |
|---|---|---|---|---|
| 1 | Report catalog breadth (18 distinct reports) | A | P2 | Trial Balance, GL, IS, BS, Customer/Vendor Subledger, AR/AP Aging, Sales by Customer/Product/Period, Purchases by Supplier, VAT Summary, Inventory Valuation, Stock Cardex, FA Register/Depreciation Schedule/Reconciliation — a shared `build_export_response` framework, not five separate implementations |
| 2 | PDF/Excel export consistency | B | P2 | 18 of 19 reports have both; **Low Stock has neither** (no `format` param at all) — trivial fix given the pattern already exists |
| 3 | Detail-level rollup correctness | A | P2 | `test_report_detail_level_rollup.py` — rollup re-sums independently, Balance Sheet identity (`assets_total == total_liabilities_and_equity`) proven to survive rollup, not assumed |
| 4 | Dashboard (KPIs, fiscal-year-aware, trend chart) | A | P2 | Genuinely reads `company.fiscal_year_start_month`, not hardcoded calendar year |
| 5 | Global search (cross-entity) | A | P2 | `SearchService.search()` — Partners/Products/Quotations/Orders/Invoices/POs/Bills, permission-gated, tested |
| 6 | Arabic/English i18n + RTL | A | P1* | `ar.json`/`en.json` both exactly 767 lines (structurally parallel); zero legacy physical `pl-`/`pr-` classes remain anywhere — genuine RTL, not superficial. *Would be a real risk if wrong for a Saudi-market demo; verified not wrong |
| 7 | Navigation consistency (`ERPListView` adoption) | A | P2 | Used across 13 route files incl. Accounting/Inventory/Purchasing main lists — the older doc's "bespoke tables" finding is stale; remaining hand-rolled tables are financial report grids inside a separate shared `ReportView`, not raw unstate-managed markup |
| 8 | Error/loading/empty states | A | P1* | `isLoading`/`isError`/`onRetry`/empty all wired via shared `ReportView`/`ERPListView` props on every page spot-checked; the older "silent blank table on failure" finding did not reproduce |
| 9 | Destructive-action confirmations | A | P1* | Fixed asset disposal requires a modal (date + accounts) before firing; role/category delete both use a shared `ConfirmDialog` |
| 10 | Searchable-picker (`EntitySearchSelect`) coverage | D | **P1** | Correctly scoped to 9 product/asset pickers, but the **same UX gap persists elsewhere**: customer picker (quotation/order headers), vendor picker (PO headers), and GL account pickers (journal entry lines, subledger filters) all still use plain, unfiltered `<Select>` — exactly the daily-use, fastest-growing-list pickers a bookkeeper touches constantly |
| 11 | Frontend form validation (`zod`/`react-hook-form`) | F | **P1** | Both libraries installed in `package.json`, **zero usage anywhere** (`useForm(`/`zodResolver(` grep = 0 matches) — every form is hand-rolled `useState`; bad input (negative qty, malformed VAT number) surfaces only as a raw backend error after a failed save |

**Reporting/UX top finding**: this is the area where the project has most clearly
outgrown its own stale documentation — the old UI/UX audit's Critical/High findings
(no company switcher, no Sales Order/Invoice lists, silent error states, bespoke
tables) are now resolved. The two real remaining gaps are narrow-scope versions of
work already proven to succeed once (`EntitySearchSelect` for 9 files; extend to
customer/vendor/GL pickers) and installed-but-idle tooling (`zod`+`react-hook-form`;
wire it into the highest-traffic transaction-line forms first).

---

## 5. Cross-Cutting Integration Audit

Tracing the flows the brief specifically asked about, using evidence gathered across
all module audits above (not re-derived, cross-referenced):

**PURCHASE**: Supplier → PO (real threshold approval) → partial/full Goods Receipt
(data-driven status recompute) → Inventory increase (real, cost-carrying) → auto-
generated Vendor Bill at PO price ("clean 3-way match by construction") → AP liability
→ real posted Journal Entry → Payment (row-locked allocation, real JE) → Reports
(Purchases by Supplier, reconciled to Trial Balance). **Verdict: fully integrated**,
each link backed by a real service call and at least one test proving it, not a manual
bridge. The one break in the chain: **no PO cancel path** and **audit logging drops off**
after short-close/reopen.

**SALES**: Customer → Quotation → confirm → Sales Order (real edit/cancel pre-invoice)
→ partial/full Invoice → Inventory issue (COGS journal entry posted) → AR receivable →
real posted Journal Entry → Receipt/Payment (concurrency-safe allocation) → Reports
(by-customer with payment/balance columns). **Verdict: fully integrated** on the same
standard as Purchasing. The break: **VAT is not actually computed from a real rate**
(hardcoded 15% on every line, both backend and frontend), and **ZATCA's cryptographic
stamp/gateway remain sandbox-only** — both are compliance-shaped gaps sitting inside an
otherwise-real pipeline, not architectural gaps.

**INVENTORY**: Purchase receipt → stock increase → valuation (FIFO/average, both real)
→ feeds COGS on sale. **Verdict: fully integrated, with one confirmed correctness bug.**
The manual `/stock/receive` endpoint remains a permission-gated but *unaudited*,
*reason-less* side door; more materially, **this audit's own regression run proved a
real concurrency bug** on the very first link in the chain — two simultaneous
first-time receipts of the same product at the same location can throw a
`UniqueViolationError` instead of both succeeding, because the row-lock in
`get_or_create_for_update` cannot protect a row that doesn't exist yet (§4.4 item 2).

**FIXED ASSETS**: Acquisition (real JE) → Asset Register → Asset Subledger (Fixed Asset
Card) → Depreciation (idempotent, JE-posting) → Accumulated Depreciation → GL →
financial statements, with a **dedicated reconciliation report proven equal to the GL
balance by test** — this is the single most rigorously integrated flow in the system.
**Verdict: fully integrated for everything after acquisition.** The one real break:
**acquisition itself is 100% standalone** — there is no link from a Purchase
Order/Vendor Bill to creating a Fixed Asset, so every capex purchase means duplicate
manual entry across two modules.

**ACCOUNTING**: Source transaction → Journal Entry → General Ledger → Trial Balance →
P&L → Balance Sheet. **Verdict: fully integrated and the best-tested chain in the
system** — detail-level rollup is proven invariant, subledgers are proven to reconcile
to GL by direct test assertion, not by construction alone. The break: **fiscal periods
are enforced in the backend but unreachable from the product** — a period can never
actually be closed by a user, so in practice this whole layer of control is dormant.

---

## 6. Accounting Integrity Summary

- Chart of Accounts hierarchy, posting restrictions, JE balance enforcement: **solid,
  tested, real invariants** (not just plausible-looking totals).
- Report detail-level rollup (1-4) does **not** change totals — proven by direct test
  assertion (`test_report_detail_level_rollup.py`), the exact property the brief asked
  to verify.
- Subledger-to-GL and Fixed-Asset-to-GL reconciliation are both **directly tested**,
  not assumed — `test_payments_subledger_m1b_smoke.py` and `test_fixed_assets.py`
  contain literal `assert subledger_total == gl_balance` style assertions.
- No financial transaction silently bypasses GL anywhere checked (Sales, Purchasing,
  Payments, Fixed Assets all post real, immediately-posted journal entries).
- **The two real accounting-integrity gaps are VAT computation and fiscal-period
  closing** — both P0, both about a control existing in name but not being real
  (VAT: a selectable-looking rate that's actually ignored; periods: enforcement code
  with no way to ever trigger it).

---

## 7. Critical Security/Compliance Risks

1. **2FA cannot actually be enabled by a user** (P0) — the verification path is real
   and tested, but there's no enrollment flow, so as shipped "2FA support" is not a
   usable feature.
2. **No password reset, no login lockout** (P0) — baseline commercial-product hygiene,
   currently absent entirely.
3. **No server-side session revocation** (P1) — a compromised access token cannot be
   killed; refresh tokens are minted but never consumable (dead half-feature).
4. **Audit trail covers roughly half the system's financial actions** (P0) — Sales
   invoicing/credit notes, all of Inventory, all of Fixed Assets, and Payments have
   zero audit-log coverage, while Accounting/Identity/parts of Purchasing do.
5. **116 unpushed commits** (P1, operational not code-level) — the entire project
   exists in exactly one place.

None of these are RLS/multi-tenancy problems — that specific engine (76 permissions, 61
`FORCE ROW LEVEL SECURITY` statements, zero detected cross-tenant leakage) is the
strongest-verified part of the whole system. The risk is entirely in account-lifecycle
hygiene and audit completeness sitting around that solid core.

---

## 8. Phase-One Definition of Done

Each item below is written to be objectively testable, per the brief's instruction —
no vague "system is ready" statements.

**FUNCTIONAL**
- [ ] VAT is computed from a real, configurable tax rate on every sales/purchase line
      (not a hardcoded 15%), with the frontend's rate picker bound to real `TaxRate`
      rows.
- [ ] A user can open and close a fiscal period from the UI; posting to a closed
      period is blocked (already true) and is demonstrated end-to-end, not just at the
      API layer.
- [ ] Draft Journal Entries can be edited or deleted before posting.
- [ ] Purchase Orders and Quotations/Invoices have a working `:cancel` path matching
      their modeled `cancelled` status.
- [ ] Fixed Asset acquisition can be created from an approved Vendor Bill line, not
      only standalone.
- [ ] Fixed Asset categories carry default GL accounts, applied (with override) at
      asset creation.
- [ ] `/stock/receive` requires a reason/reference and is audit-logged.

**SECURITY**
- [ ] A user can self-enroll in 2FA (generate secret, scan QR, confirm code) through
      the product.
- [ ] A password-reset flow exists end-to-end.
- [ ] Repeated failed logins trigger a lockout/cooldown.
- [ ] A logout/session-revocation endpoint exists and actually invalidates the token
      server-side (or refresh-token issuance is removed until one does).

**ACCOUNTING**
- [ ] (Already met) Trial Balance, Income Statement, Balance Sheet, and their detail-
      level rollups reconcile — proven by existing tests.
- [ ] (Already met) Subledgers and Fixed Asset register reconcile to GL — proven by
      existing tests.

**INTEGRATION**
- [ ] (Already met) Purchase-to-Pay and Order-to-Cash both trace end-to-end with real
      service calls and tests at every link, per §5 above.

**AUDIT/COMPLIANCE**
- [ ] `AuditLogRepository.record()` covers invoice issuance, credit/debit notes,
      inventory adjustments/transfers, and fixed-asset depreciation/disposal — the
      financially material actions currently unaudited.
- [ ] ZATCA is either explicitly scoped out of "Phase One Sellable" in writing, or a
      real CSID/signing/gateway integration replaces the sandbox stack.

**TESTING**
- [ ] `get_or_create_for_update` (`inventory/infrastructure/repositories.py:106-115`)
      is fixed to handle concurrent first-time inserts (`INSERT ... ON CONFLICT` or a
      retry-on-`IntegrityError` wrapper) — root cause identified by this audit, not
      still "flaky."
- [ ] At least one 403/permission-denial test exists per module for a representative
      mutating action.

**DOCUMENTATION**
- [ ] `docs/project-progress.md`'s structured Completion Matrix is regenerated from
      current source (or retired in favor of the narrative log alone, which is
      current).
- [ ] `docs/11-testing.md` is updated — it still describes a 43-test suite; the real
      count is 10x that.
- [ ] A backup/recovery runbook is added to `docs/14-deployment.md`.

**OPERATIONAL**
- [ ] `origin/main` is brought current — 116 commits pushed, or an explicit decision
      documented for why not.
- [ ] A CI pipeline runs tests/lint on push (currently absent).

---

## 9. P0/P1/P2 Gap Matrix

Consolidated from all module sections above (§4). Estimated effort for each line is
folded into the Three-Day Closure Plan (§10) rather than repeated per-row here, since
every P0/P1 item maps to a specific day and bullet below.

| Priority | Module | Gap | Blocking? |
|---|---|---|---|
| P0 | Accounting/Sales/Purchasing | VAT hardcoded, not really computed | YES |
| P0 | Accounting | Fiscal periods unreachable (no UI/tests) | YES |
| P0 | Security | 2FA has no enrollment path | YES |
| P0 | Security | No password reset / lockout | YES |
| P0 | Security | Audit trail missing across ~half the system | YES (compliance) |
| **P0** | **Inventory** | **Real concurrency bug in first-time stock receipt (`UniqueViolationError`), confirmed by this audit's regression run** | **YES (data-correctness)** |
| P0* | Sales/ZATCA | Sandbox-only, not production-certified | Only if KSA go-live is in scope |
| P1 | Accounting | JE drafts can't be edited/deleted | recommended |
| P1 | Purchasing | No PO `:cancel` | recommended |
| P1 | Sales | Quotation/Invoice `cancelled` unreachable | recommended |
| P1 | Fixed Assets | Categories don't carry GL accounts | recommended |
| P1 | Fixed Assets | Acquisition not linked to Purchasing | recommended |
| P1 | Inventory | `/stock/receive` has no reason field | recommended |
| P1 | Security | Refresh tokens minted but unusable; no logout | recommended |
| P1 | *(all)* | Sparse/missing audit trail (Sales, Inventory, Fixed Assets, Payments, ZATCA) | recommended |
| P1 | Frontend/UX | `EntitySearchSelect` not extended to customer/vendor/GL-account pickers | recommended |
| P1 | Frontend/UX | `zod`+`react-hook-form` installed but unused anywhere — no field-level validation | recommended |
| P2 | Reporting | Low Stock report has no PDF/Excel export (only gap in an otherwise-complete framework) | deferred |
| P2 | *(all)* | No serial/lot tracking, no multi-currency | deferred (by design) |
| P2 | Ops | No CI pipeline | deferred |
| P2 | Docs | Stale Completion Matrix, stale testing doc | deferred |
| P1 (ops) | Git | 116 unpushed commits | recommended before any handoff |

---

## 10. Three-Day Closure Plan

The original 3-Day Brief (P0-1 through P0-9) already ran and is fully committed (§3) —
this is a **new** plan for what this audit found still open. Allocation follows the
actual gap shape found, not an even split: Day 1 is accounting/security correctness
(the P0s), Day 2 is integration/audit-trail hardening plus the two proven-pattern UX
extensions, Day 3 is regression, reconciliation, and documentation truing-up.

### Day 1 — P0 functional/accounting/security correctness
- Wire real per-line VAT: connect `tax_rate_id` to an actual `TaxRate` lookup in
  `sales/application/services.py` and `purchasing/application/services.py`; replace the
  frontend's placeholder `STANDARD_VAT_TAX_RATE_ID` (8 files) with a real tax-rate
  picker bound to the company's seeded `TaxRate` rows.
- Build the minimum fiscal-period UI: a company-settings screen to create/close/reopen
  a period, wired to the existing (already-correct) backend enforcement; add the test
  coverage that currently doesn't exist at all.
- Ship 2FA enrollment: `POST /auth/2fa/setup` (generate secret + QR) + `/confirm`
  (verify first code, flip `is_2fa_enabled`) — the verification half already works and
  is tested; this closes the missing half.
- Ship password-reset (request + confirm-with-token) and basic login-lockout
  (failed-attempt counter + cooldown).
- Fix the confirmed inventory concurrency bug: change
  `get_or_create_for_update` (`inventory/infrastructure/repositories.py:106-115`) to
  `INSERT ... ON CONFLICT (product_id, location_id) DO UPDATE SET id = stock_quant.id
  RETURNING *` (or catch `IntegrityError` and retry the `get_for_update` once) instead
  of check-then-insert. Small, isolated, and this project already has the exact
  precedent (the admin-role permission sync fix used the same `ON CONFLICT` pattern for
  an unrelated race).

### Day 2 — Integration/audit-trail hardening + proven-pattern UX extension
- Extend `AuditLogRepository.record()` into Sales (invoice issuance, credit notes,
  order cancel), Inventory (`/stock/receive`, transfers, cycle-count approval), and
  Fixed Assets (depreciation run, disposal) — the pattern already exists in Accounting/
  Identity/Purchasing; this is applying it, not designing it.
- Add a `:cancel` endpoint to Purchase Orders (same shape as the already-built
  short-close) and close the two unreachable `cancelled` states on Quotation/Invoice.
- Give draft Journal Entries an edit/delete path.
- Add a required reason/reference field to `/stock/receive`.
- Extend `EntitySearchSelect` to customer/vendor pickers (quotation/order/PO headers)
  and the GL-account picker on journal-entry lines — same component proven on 9 files
  already, no new pattern.
- Wire `zod`+`react-hook-form` into the highest-traffic transaction-line forms (sales
  quotation/order lines, PO/vendor-bill lines, journal-entry lines) — dependencies are
  already installed and idle.
- Implement `POST /auth/refresh` and a logout/revocation endpoint (or remove
  refresh-token issuance if not being completed this cycle — don't ship unusable
  attack surface).

### Day 3 — Full regression, reconciliation, documentation, release prep
- Full backend regression (`pytest`) + `ruff` + frontend `tsc`/`eslint`/`next build`;
  confirm `test_stock_quant_concurrency.py` now passes consistently (Day 1 fix) —
  run it standalone 5-10x back-to-back, not just once, since the whole point was that
  it only failed under real concurrent load.
- Add category-level default GL accounts to Fixed Asset categories (with per-asset
  override) — closes the one real data-integrity gap in an otherwise well-reconciled
  module.
- Add PDF/Excel export to the Low Stock report (closes the only gap in an otherwise
  complete export framework).
- Regenerate `docs/project-progress.md`'s structured Completion Matrix from current
  source (or retire it in favor of the narrative log, which stays current); update
  `docs/11-testing.md` (still describes a 43-test suite; real count is ~10x that); add
  a backup/recovery section to `docs/14-deployment.md`.
- **Push all 116+ pending commits to `origin/main`** — do this early on Day 3, not last,
  since it's zero-risk and removes the single-point-of-failure exposure immediately.
- Live walkthrough of the closed gaps (VAT on a real invoice, a period close, 2FA
  enrollment, a cancelled PO) before declaring Phase One done — this project's own
  established discipline (`docs/master-execution-plan.md` §H: Implemented + Tested +
  Integrated + Usable + Verified + Documented) applies to closure work exactly as it did
  to every prior milestone.

If ZATCA production certification is required for Phase One (not just the sandbox
pipeline), that is its own compliance project — real CSID onboarding, ECDSA signing,
live gateway integration — and does not fit inside this 3-day window; it should be
scoped and scheduled separately, with Phase One declared sellable domestically/
non-ZATCA-critical in the meantime if that's commercially acceptable.

---

## 11. Recommended Next Action

Every P0 in this report is a bounded addition to already-correct surrounding code, not
a redesign — which means the highest-leverage single next step is **Day 1 of §10 in
full**. Two items on that day compete for "most urgent": VAT (independently found by
two separate audits, touches every invoice, the difference between "works for a demo"
and "correctly invoices a real VAT-registered transaction") and the inventory
concurrency bug (not theoretical — this audit's own regression run reproduced it live,
with an exact stack trace and a known-good fix pattern already used elsewhere in this
codebase). Start with whichever is cheaper to ship first — the concurrency fix is a
single method, likely under an hour; VAT touches more files but is architecturally
simple (wire an already-existing table to already-existing code paths) — and land both
before anything else on Day 1.

**Based on this audit, what is the single highest-priority action we should execute
next to close ERP SYSTEM PHASE ONE?**
