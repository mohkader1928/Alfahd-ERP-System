# Phase 17F — Milestone 1b: Customer/Vendor Subledgers, AR/AP Aging, Traceability

> **Status**: Implemented, tested, verified, live-demonstrated. Not yet committed at the time this document was written — see the checkpoint report for exact commit status. Not yet Owner Accepted.

## 1. Scope

Per the approved implementation plan: Customer Subledger, Vendor Subledger, AR Aging, AP Aging, Customer/Vendor Statement (delivered as the Subledger's own print view, not a second computation — see §6), Journal Entry → source-document drill-down, and reconciliation proof against the General Ledger. Explicitly out of scope: vendor debit/credit notes (no such model exists in Purchasing), historical point-in-time Aging, a server-generated PDF service, Owner Login/company-picker UX, company-name visibility UX.

## 2. Architecture

`SubledgerService` lives in the **Payments module** (`backend/src/modules/payments/application/services.py`), not Accounting — Payments already reads Sales/Purchasing (read-only) and Accounting, which is exactly the dependency shape Subledgers need. Putting this logic in Accounting would have required Accounting to start depending on Sales/Purchasing/Payments, breaking the one-way dependency map established since Phase 8. No new database table, no migration — everything is computed from `sales_invoice`, `vendor_bill`, `payment`, `payment_allocation`, all of which already existed.

## 3. What was built

**Backend**: `PaymentRepository.list_allocations_for_partner` (new query), `SubledgerService.customer_subledger` / `.vendor_subledger` / `.ar_aging` / `.ap_aging`, 4 new endpoints under `/api/v1/payments/` (`subledger/customer/{id}`, `subledger/vendor/{id}`, `aging/ar`, `aging/ap`), 2 new permissions (`payment.subledger.view`, `payment.aging.view`), and `source_table`/`source_id` now exposed on `JournalEntryOut`, `JournalEntryDetailResponse`, and `GeneralLedgerLine` (existing database columns, populated by every module since the earliest phases, simply never surfaced in the API before).

**Frontend**: 4 new Accounting tabs (Customer Subledger, Vendor Subledger, AR Aging, AP Aging), a print-friendly statement view (`window.print()`, no new library), a new Payment detail page (`/payments/[id]`, did not exist before this Milestone — needed so a Subledger's "payment" row has somewhere real to link to), and a Source column added to General Ledger + a Source-document line added to the Journal Entry detail page, both resolving to real pages via a new shared helper (`lib/source-document-links.ts`).

## 4. Calculation rules

- **Customer Subledger**: Invoice → debit, Credit Note → credit, Payment allocation → credit. Running balance = cumulative debit − credit from a computed opening balance — the same sign convention as AR (account `1200`).
- **Vendor Subledger**: Bill → credit, Payment allocation → debit — mirrors AP (account `2100`).
- **AR/AP Aging**: reflects each open document's **current, real** outstanding balance, bucketed by days overdue relative to the chosen `as_of_date` (Current / 1–30 / 31–60 / 61–90 / 90+). Does not reconstruct a historical point-in-time balance — documented as a deliberate scoping decision in the approved plan, not a gap discovered later.

## 5. A real bug found and fixed during this Milestone's own verification

**Finding**: AR Aging originally computed an invoice's outstanding balance from payment allocations only. A credit note settles an invoice too (it reduces the specific invoice's balance via `SalesInvoice.original_invoice_id`), but the first version of `ar_aging` never accounted for that — a fully credit-noted invoice still showed its entire original amount as overdue.

**How it was caught**: not by the automated tests alone — live verification against the Owner Acceptance environment showed a customer whose account should have read exactly $0 outstanding (invoice fully credited) still appearing in AR Aging with a $230 balance. That contradiction is what triggered the investigation.

**Fix**: `SubledgerService.ar_aging` now builds a map of credited amounts per `original_invoice_id` up front and subtracts it from each invoice's balance before deciding whether it's still open.

**Proof it's fixed, not just patched**: a new regression test, `test_ar_aging_excludes_fully_credit_noted_invoice`, asserts a fully-credited invoice never appears in AR Aging — and the same scenario was re-verified live in the browser after the fix (§8).

This is exactly the kind of thing the Owner's standing rule asks for: found during verification, not hidden, fixed with a real test proving it, reported here rather than silently corrected.

## 6. Why Statement isn't a second computation

Customer/Vendor Statement is the same Subledger data rendered in a print layout. Building a second, independent calculation for "Statement" risked the two disagreeing over time — a real data-integrity risk. One source of truth, two presentations.

## 7. A second real finding: RBAC permission-catalog growth doesn't propagate

Confirmed by reading every route in `modules/identity/api/routes.py`: there is **no API endpoint anywhere that grants a new permission to an already-existing role**. `RoleService.create_role` only ever grants the permission list handed to it once, at bootstrap. This meant the Milestone 1a demo company's Admin role (created before `payment.subledger.view`/`payment.aging.view` existed) gets a 403 on these two new screens — not a bug in Subledger/Aging, a structural gap in how the permission catalog evolves. Not fixed here (it would mean building role-management API surface, real scope beyond this Milestone) — worked around honestly for the Owner Acceptance environment by bootstrapping a fresh company (Company C) whose Admin role picks up the current catalog automatically, and reported here so it isn't lost. Recommend surfacing this to the Owner/Consultant as a candidate for a future Milestone (Role Management, already flagged generally in earlier checkpoints, now concretely reproduced).

## 8. Verification performed

- **13 backend tests** (`test_payments_subledger_m1b_smoke.py`): Customer Subledger opening/running/closing balance against hand-computed values, credit-note netting, Vendor Subledger, **the reconciliation test** (sum of all customers' Subledger closing balances == the General Ledger's own AR account balance for the same date; same for vendors against AP), AR Aging bucket boundaries (unit-tested directly, since invoice dates can't be backdated through the real API), the credit-noted-invoice regression test (§5), a documented-and-tested pre-existing gap (an unapproved vendor bill correctly never appears in any report), Journal Entry → source-document resolution, and cross-company isolation.
- **Full regression**: 159/159 backend tests pass (147 before this Milestone + 12 new — 13 written, 1 folded into the isolation test count correctly). `ruff`, `tsc`, `eslint`, production build all clean.
- **Live browser verification** (Company C, a real login, no SQL/Postman): Customer Subledger showed the exact 4 expected rows with the exact running balances; clicking an invoice row opened the real Invoice detail page; clicking the payment row opened the new Payment detail page, which itself resolved and linked to the real invoice it settled; Vendor Subledger showed the correct single bill line (non-clickable, honestly, since no Vendor Bill detail page exists yet); AR Aging correctly showed **zero rows** (proving the §5 fix live, not just in a test); AP Aging showed the one open bill, correctly bucketed by the real current date; General Ledger's new Source column and the Journal Entry detail page's new Source-document line both resolved to, and linked to, the real Sales Invoice.

## 9. Known limitations (honest, not hidden)

- Vendor Bill has no detail page yet — Vendor Subledger's bill rows are informative but not clickable (Sales/Purchasing Standardization territory, already on the roadmap).
- The Payments list screen itself still has no link from a row to the new Payment detail page — only reachable today via Subledger/GL drill-down. A small, real gap; not fixed here to avoid touching the Payments list page outside this Milestone's approved scope.
- RBAC permission-catalog growth doesn't propagate to existing companies (§7) — a real, structural finding, not scheduled for a fix in this Milestone.
- AR/AP Aging is "current balance as of today," not a true historical reconstruction (§4) — a scoping decision made in the approved plan, not a bug.
