# Phase 17D — Payments

Renumbered from the original blueprint's "Phase 17C — Payments" (see
`docs/project-progress.md` §1 for why: an unplanned security phase took
the "17C" slot instead and shipped as Phase 17C-RLS).

**Status**: business-complete for the scoped v1 (record → allocate → post
→ track balance → settle, for both customer and vendor payments,
including real concurrency safety). Delivered in two passes: an initial
implementation, then a re-audit (this document's current state) that
closed two real gaps found by checking the full business lifecycle
end-to-end rather than assuming CRUD + a form meant "done." Not committed
yet.

## 1. Scope

A minimal, correct Payments module: record a customer payment against one
or more sales invoices, record a vendor payment against one or more
vendor bills, post the matching cash/bank journal entry, and — as of the
re-audit pass — make each document's paid/partial/unpaid status visible
and safe under concurrent payments. This unblocks AR/AP aging and
customer/vendor statements (deferred to a later phase) without building
them yet — see `docs/17-erp-standardization-master-blueprint.md` §18/§21
for the original dependency analysis that put Payments first.

## 2. Architecture

Module `backend/src/modules/payments/`, following the same
domain/application/infrastructure/api layering as every other module.
Depends on Identity (partners), Accounting (`JournalEntryService`,
`AccountRepository`), Sales (`SalesInvoiceRepository`, read-only), and
Purchasing (`VendorBillRepository`, read-only) — a superset of Sales' and
Purchasing's existing dependency shape, not a new pattern. Deliberately
one-way: Sales/Purchasing have **no** dependency back on Payments — an
invoice's paid status is computed by *Payments* querying *Sales*, never
the reverse, so the module dependency graph stays acyclic (see §5 for why
this ruled out putting `amount_paid` directly on `SalesInvoiceOut`).

## 3. Database changes (migration `5955ce0f8dd6`)

- `sales_invoice.due_date` (nullable) — additive, no backfill.
- `vendor_bill.due_date` (nullable) — additive, no backfill.
- `payment` — `id, company_id, branch_id, partner_id, payment_type
  (customer|vendor), number, payment_date, amount, currency_code,
  account_id, reference, journal_entry_id, created_by, created_at`.
  `UNIQUE(company_id, number)`, `CHECK(amount > 0)`.
- `payment_allocation` — `id, company_id, payment_id, sales_invoice_id,
  vendor_bill_id, amount`. `CHECK` enforces exactly one of
  `sales_invoice_id`/`vendor_bill_id` is set per row (never both, never
  neither) — real FK constraints to both target tables, not a polymorphic
  `(document_type, document_id)` pair, so referential integrity is
  enforced by Postgres itself.
- Both new tables get `ENABLE`+`FORCE ROW LEVEL SECURITY` and a
  `company_isolation` policy **in this same migration** — not retrofitted
  after the fact, the exact mistake Phase 16A/16B had to fix for
  pre-existing tables.
- New seeded permissions: `payment.view` (screen), `payment.create`
  (action) — added to `PERMISSION_CATALOG`
  (`src/shared/infrastructure/db/seed.py`). Like every prior permission
  addition (17A/17B), this is only automatically granted to companies
  bootstrapped *after* this change; existing companies' Admin role isn't
  retroactively updated (same limitation those phases already carried,
  not new to Payments).

## 4. Business rules enforced

- **Allocation can't exceed the target document's outstanding balance.**
  `PaymentRepository.sum_allocated_for_sales_invoice`/
  `sum_allocated_for_vendor_bill` sums existing allocations before
  accepting a new one; exceeding `total_amount` raises `OverAllocationError`
  (422).
- **Allocation can't exceed the payment's own amount.** The unallocated
  remainder becomes an implicit credit on the payment (not an error) —
  only allocating *more* than the payment is worth is rejected.
- **Allocation must match the payment's own partner.** A customer payment
  can only allocate to sales invoices belonging to that same customer
  (`InvalidAllocationTargetError`, 422) — prevents crediting the wrong
  customer's balance even if the invoice ID is guessable.
- **Cash/bank account must belong to the same company.**
- **Concurrent payments against the same document can't jointly
  over-allocate it** (re-audit finding, closed — see §5).

## 5. Re-audit findings and fixes

The initial implementation passed 6/6 tests and all standard checks, but
a deliberate re-audit — walking the exact end-to-end scenarios in
`docs/project-progress.md`'s continuation directive rather than trusting
"tests pass" as proof of business-completeness — found two real gaps:

**Finding 1 — no way to see a document's payment status.**
`SalesInvoiceOut`/`VendorBillOut` had no `amount_paid`/`balance_due`/
`payment_status` field, and there was no endpoint to compute them either.
An invoice could be fully paid and nothing in the API would show it.
Putting these fields directly on Sales'/Purchasing's own response schemas
would have required those modules to query Payments — creating the exact
circular module dependency the architecture has avoided since Phase 9.
**Fix**: `GET /payments/balance/sales-invoice/{id}` and
`GET /payments/balance/vendor-bill/{id}`, computed on demand
(`total_amount`, `amount_paid`, `balance_due`, `payment_status`) from
`SUM(payment_allocation.amount)` — never a stored/persisted balance
column, which would reintroduce the exact denormalized-state-drift risk
Phase 16B was created to eliminate. `payment_status` is derived, not
stored: `unpaid` (`amount_paid <= 0`), `paid` (`balance_due <= 0`),
`partially_paid` (otherwise).

**Finding 2 — concurrent payments could jointly over-allocate the same
invoice.** The allocation check (`sum_allocated_for_X` compared against
`total_amount`) read the current sum without any row lock. Two
simultaneous payment requests against the same invoice could both read
"not yet over-allocated," both pass the check, and both commit — a
classic TOCTOU race, the same *class* of bug Phase 16B fixed for
duplicate invoice creation (there, a DB partial unique index; here, a
row lock, since the invariant being protected is an aggregate sum, not a
single-row uniqueness). **Fix**: `SalesInvoiceRepository.
get_by_id_for_update()` / `VendorBillRepository.get_by_id_for_update()` —
`SELECT ... FOR UPDATE` on the target document row, used only by
`PaymentService`'s allocation check. The second of two concurrent
requests now blocks until the first's transaction ends, then re-reads the
now-current allocation sum. **Proven, not just reasoned about**:
`test_concurrent_payments_cannot_jointly_overallocate_same_invoice` fires
two real simultaneous `POST /payments` calls (via `asyncio.gather`) each
trying to allocate the full invoice total — asserts exactly one succeeds
(201) and one is correctly rejected (422), and that the final allocated
total never exceeds the invoice total. Passes.

**A third item was evaluated and intentionally not built**: a real
invoice/bill picker in the UI. This was originally deferred (see the
"before" version of this doc) because Sales had no `GET /invoices` list
endpoint. During the re-audit, adding that one list endpoint (mirroring
the pattern Purchasing's `GET /vendor-bills` already used, plus a
`partner_id` filter added to both) was judged a small, justified,
same-shape addition — not scope creep into Sales Standardization — so it
*was* built, and the picker now uses it (see §9). This is called out
explicitly because it's the one place this phase's boundary moved after
the initial cut, and the reasoning is recorded here rather than silently
expanding scope.

## 6. Accounting posting

Reuses `JournalEntryService.create_draft_entry` + `.post_entry`, journal
code `BANK` (already seeded for every company, `journal_defaults["BANK"]`
in `ChartOfAccountsService.seed_default_journals`) — no new journal
needed.

- Customer payment: Dr cash/bank account, Cr `1200` (Accounts Receivable).
- Vendor payment: Dr `2100` (Accounts Payable), Cr cash/bank account.

Posted synchronously in the same request/transaction as the payment
record and its allocations — no draft/post two-step for v1. The route
commits exactly once, after the payment, allocations, and journal entry
have all flushed within the same session; any exception anywhere in that
chain propagates out before the commit is reached, so nothing partial is
ever persisted (verified by the concurrency test above, whose rejected
request leaves zero trace — no orphan payment row, no orphan journal
entry).

## 7. API surface (`/api/v1/payments`)

- `POST /payments` — create + post in one call.
- `GET /payments` — list, optional `?payment_type=customer|vendor` filter.
- `GET /payments/{id}` — detail, including allocations.
- `GET /balance/sales-invoice/{id}` — computed payment status (added in
  the re-audit pass, §5).
- `GET /balance/vendor-bill/{id}` — same, vendor side.

Also added to **Sales** (`/api/v1/sales/invoices`, list with optional
`?partner_id=` filter) and **Purchasing** (`/api/v1/purchasing/vendor-bills`
gained the same `?partner_id=` filter, list endpoint itself already
existed) — small, same-shape additions needed for the picker in §9, not a
broader standardization pass.

## 8. Permissions

`payment.view` (screen) and `payment.create` (action), gating list/detail/
balance and create respectively — same `require_permission()` pattern as
every other module. The new Sales/Purchasing list endpoints reuse those
modules' existing permission codes (`sales.invoice.create`,
`purchasing.vendor_bill.view`) rather than inventing new ones.

## 9. Security / RLS

Both new tables verified against the real `erp_app` role (never a
superuser substitute), confirmed at the migration level
(`FORCE ROW LEVEL SECURITY`, `company_isolation` policy present, owned by
`erp_migrate`) and at the application level
(`test_payment_isolated_across_companies` — company B gets 404 on company
A's payment, and it's absent from company B's list). The row-lock fix in
§5 was also verified under RLS — `SELECT ... FOR UPDATE` composes
correctly with `company_isolation`'s `USING` clause; a locked row from
another company is still invisible, not just unlockable.

## 10. UI screens

- `/payments` — list (search, sort, pagination, permission-gated Create —
  built on the same `ERPListView` Quotations already uses).
- `/payments/new` — create form (`FormView` shell):
  - Payment type (customer/vendor) and partner pickers, as before.
  - **Real invoice/bill picker** (re-audit addition): once a partner is
    selected, a dependent query fetches that partner's invoices (or
    bills) via the new list endpoints and offers them as options —
    replacing the original paste-the-ID-in workaround.
  - Selecting a document fetches its live balance
    (`GET /balance/...`) and shows it inline (e.g. "Outstanding balance:
    230.0000 (Unpaid)"), and defaults the payment amount to that balance
    — editable for a partial payment. Implemented as derived state
    (`amountOverride ?? balance ?? "0.00"`) rather than a `useEffect`
    syncing two pieces of state, per this project's lint rule against
    synchronous `setState` inside effects.
  - Still uses the existing hand-rolled `useState` pattern, not
    `zod`+`react-hook-form` — see §12 for why that stays deferred.
- New sidebar entry (`Banknote` icon) between Purchasing and Master Data.

## 11. Tests

`backend/tests/test_payments_m6_smoke.py` — **11 tests**: full customer
payment (with journal entry assertion), partial payment completed by a
second payment, overallocation rejected, cross-partner allocation
rejected, vendor payment against a bill, cross-company RLS isolation,
invoice balance transitioning unpaid→partially_paid→paid, vendor bill
balance reflecting paid status, Sales invoice list endpoint filtering by
partner, Purchasing vendor-bill list endpoint filtering by partner, and
the concurrent-double-payment race (§5). All run through the real HTTP
API against the real dockerized Postgres, same pattern as every other
test in this suite.

## 12. Known limitations / deferred items

- **The create form uses the existing hand-rolled `useState` pattern, not
  `zod`+`react-hook-form`.** Reconsidered during the initial
  implementation: introducing a brand-new frontend pattern with zero
  precedent elsewhere in the codebase, without a dedicated round of
  UI-specific testing budget, was judged a real risk of shipping a
  subtly broken form for comparatively low benefit over the existing,
  proven pattern every other form already uses. Still true after the
  re-audit's picker rewrite (which added real complexity — dependent
  queries, derived default values — but not complexity that needed a
  schema-validation library to manage correctly). Deferred as its own
  small, focused follow-up.
- **No refund/reversal endpoint** — overpayment sits as an unallocated
  credit on the payment record; there's no way yet to apply that credit
  to a *future* invoice or refund it. Evaluated during the re-audit and
  intentionally not built: it needs a real design decision (does a
  credit apply automatically to the next invoice, or only on request? is
  a cash refund a new payment type or a reversal of the original?) that
  doesn't have an obviously-correct minimal answer the way the two §5
  fixes did. Recorded here as genuinely deferred, not silently dropped.
- **The document picker doesn't filter out already-fully-paid
  documents** — a paid invoice still appears as a selectable option;
  attempting to allocate to it correctly fails the outstanding-balance
  check (422), so this is a UX polish item, not a correctness gap.
- **Payment methods are cash/bank-account only** — no payment gateway
  integration, matching this project's existing scope boundary.
- **A pre-existing, unrelated finding surfaced during live UI
  verification**: `components/erp/list-view/erp-list-view.tsx`'s internal
  `Button` triggers a Base UI console warning (`nativeButton` semantics)
  on *every* page that uses it, including the pre-existing Quotations
  list — confirmed not introduced by this phase. Flagged as a separate
  background task, not fixed here.

## 13. Verification performed

- Migration applied to the real dev database; `payment`/`payment_allocation`
  confirmed `FORCE ROW LEVEL SECURITY`, owned by `erp_migrate`, correct
  `company_isolation` policy. Confirmed again after a full Docker cold
  restart (`down` → `up postgres redis` → `migrate`, idempotent, no
  pending migrations → `up api/worker`).
- 11/11 Payments tests passing; **141/141 full backend suite** passing
  alongside them, confirmed on two separate runs (before and after the
  cold restart).
- Ruff clean on every new/modified backend file.
- `tsc --noEmit` and `eslint` clean on every new/modified frontend file
  (including after fixing a `react-hooks/set-state-in-effect` lint error
  caught during the picker rewrite).
- `next build` succeeds; 26 routes, including `/payments` and
  `/payments/new`.
- `/health` returns `{"status":"ok","database":true}` after cold restart;
  `alembic_version` confirmed at `5955ce0f8dd6`.
- **Live-verified in the browser, full create flow, not just page
  loads**: bootstrap → login → issued a real invoice (INV-000001,
  230.00 SAR) via the actual Sales API → `/payments/new` → selected
  "customer" type → partner picker correctly populated and filtered →
  selecting the partner correctly enabled and populated the invoice
  picker (network-confirmed: `GET /sales/invoices?partner_id=...`) →
  selecting the invoice correctly fetched and displayed "Outstanding
  balance: 230.0000 (Unpaid)" (network-confirmed:
  `GET /payments/balance/sales-invoice/{id}`) and auto-filled the amount
  field → selected a cash/bank account → **Save** → redirected to
  `/payments`, showing the real created row `PAY-000001 | Customer
  payment | 2026-08-02 | 230.0000 SAR` → re-queried the balance endpoint
  directly and confirmed it now returns `payment_status: "paid"`,
  `balance_due: "0.0000"`. A display bug found during this pass (the
  partner/document `Select` showed the raw UUID instead of the resolved
  name/number label) was fixed and re-verified live.
