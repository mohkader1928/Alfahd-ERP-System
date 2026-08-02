# Phase 17E — Accounting Standardization (Milestone 1a: General Ledger, Income Statement, Balance Sheet)

> **Status**: Milestone 1a implemented, tested, and live-verified. Not yet committed — awaiting this checkpoint's Owner approval. Milestone 1b (AR/AP Aging, Customer/Vendor Statements) is scoped but not started — see §6.

## 1. Scope of this Milestone

Milestone 1 ("Accounting Standardization") was split into two checkpointed sub-milestones rather than delivered as one large, unverified push, per the Owner's mandatory-checkpoint rule. This document covers **1a**: General Ledger, Income Statement, and Balance Sheet — the three reports that turn already-correct Journal Entry data into answers an Owner can actually read. **1b** (AR/AP Aging, Partner Statements) depends on joining Payments + Sales/Purchasing data differently and is deliberately a separate checkpoint.

## 2. Why these three, and in this combination

Trial Balance already existed (Phase 11). The single largest gap identified in the Business Core Gap Analysis (`docs/master-execution-plan.md` §D) was: *there was no way to ask "are we profitable" or "what is the business worth right now"* without reading raw Journal Entries by hand. General Ledger, Income Statement, and Balance Sheet close that gap together, and they share one underlying query engine (per-account debit/credit aggregation, already proven correct by Trial Balance's existing tests), so building them together was cheaper and more consistent than three separate efforts.

## 3. What was NOT changed

No new database tables, no new migration. Every figure in all three reports is computed on demand from the existing `journal_entry` / `journal_entry_line` / `account` / `account_type` tables — the same tables Trial Balance already reads. This was a deliberate architectural choice: a report that can't be traced back to `Journal Entry → Journal Entry Line → Account` is not trustworthy, per the Owner's explicit accounting-integrity rule.

## 4. How each report works

### General Ledger (`GET /accounting/reports/general-ledger`)
One account's movements over a date range: an opening balance (everything posted before the range), each line in range with a running balance, and a closing balance. Each line carries its Journal Entry id, so the screen's "Reference" column links straight to that Journal Entry's existing detail page — real drill-down to source, not a static number.

### Income Statement (`GET /accounting/reports/income-statement`)
Revenue, Cost of Goods Sold, Gross Profit, Operating Expenses, Operating Income, Net Income for a period. **The COGS vs. Operating Expenses split is not invented** — it uses the Chart of Accounts hierarchy the system has seeded since Phase 11 (`5000 Expenses` → `5100 Cost of Goods Sold` / `5200 Operating Expenses`): any expense account that is `5100` or nests under it is COGS; every other expense account is an Operating Expense. This means a company's own custom expense accounts are classified correctly automatically, based on where they were filed in the Chart of Accounts, not a hardcoded list.

There is currently no "Other Income/Expense" bucket because no such accounts exist yet in the seeded Chart of Accounts — the report shows Net Income = Operating Income rather than inventing a zero line item to look more complete than it is.

### Balance Sheet (`GET /accounting/reports/balance-sheet`)
Assets, Liabilities, Equity as of a date. **Important, explicitly flagged limitation**: the system has no period-closing mechanism yet that moves a finished year's profit into Retained Earnings (`FiscalPeriodService.close_period` only locks a period against new postings — it does not post closing entries). Rather than let the Balance Sheet quietly fail to balance, this report computes net income since the company's inception as an explicit **"Current Earnings (unclosed)"** line inside Equity. This is derived, read-only arithmetic — no entries are posted, nothing is mutated — and it guarantees the one non-negotiable identity (**Assets = Liabilities + Equity**) always holds. When a real period-close/closing-entry feature is eventually built, this line is exactly what it would formalize into a posted transfer to Retained Earnings; until then, this is the honest, correct interim answer rather than a workaround that hides the gap.

## 5. Verification performed

- **6 new backend tests** (`backend/tests/test_accounting_reports_m1a_smoke.py`), all against a real posted business scenario (inventory purchase → capital injection → a sale with VAT → its COGS → an operating expense), asserting exact figures — not just "200 OK":
  - General Ledger opening balance + running balance + closing balance.
  - Income Statement's Revenue/COGS/Gross Profit/OpEx/Net Income figures, and that COGS and OpEx are correctly split by account code.
  - Balance Sheet: **`assets_total == liabilities_total + equity_total`** asserted directly — the identity itself, not just individual numbers.
  - Cross-company isolation: a second, unrelated company sees zero on all three reports despite the first company's real activity.
  - Permission enforcement (401 without auth).
- **Full regression**: 147/147 backend tests pass (141 prior + 6 new), `ruff check src/ tests/` clean, `tsc --noEmit` clean, `eslint` clean, production `next build` clean.
- **Live browser verification** (not just the automated tests): bootstrapped a fresh company, posted the same 5-entry scenario via the running API, then opened `/accounting` in a real browser session and read each of the three new tabs directly:
  - Income Statement showed Revenue 1000.0000 / COGS (600.0000) / Gross Profit 400.0000 / OpEx (100.0000) / Net Income 300.0000.
  - Balance Sheet showed Assets 5450.0000 = Liabilities 150.0000 + Equity 5300.0000 (Capital 5000 + Current Earnings 300), with the total-vs-total identity visibly matching.
  - General Ledger (Cash account, from 2026-05-10) showed Opening balance 4000.0000, one movement (-100.0000 on 2026-05-15), Closing balance 3900.0000, and its Reference cell linked to `/accounting/journal-entries/<real-id>` — confirmed by reading the link's actual `href`, not assumed.
  - The account picker resolves to real labels ("1100 — Cash and Bank"), not raw IDs — reusing the exact `SelectValue` resolver pattern established (and the bug fixed) in Phase 17D.

## 6. Explicitly deferred to Milestone 1b (not started)

- **AR Aging / AP Aging** — who owes what, how overdue, bucketed by days-past-due. Depends on joining Payments' existing balance logic with Sales Invoice / Vendor Bill due dates (both already added in Phase 17D).
- **Customer Statement / Vendor Statement** — a partner's own running balance across invoices, credit notes, and payments in one screen.

These were not attempted in this checkpoint because they read from a genuinely different shape of data (partner-scoped, cross-module) than General Ledger/Income Statement/Balance Sheet (account-scoped, single-module), and bundling them in would have meant a larger, harder-to-verify change — against the Owner's explicit "checkpoint, don't batch weeks of work" instruction.

## 7. Known limitations

- No period-closing/closing-entry mechanism (see §4's Balance Sheet note) — the "Current Earnings (unclosed)" line is the correct, honest interim answer, not a bug, but it means the Balance Sheet does not yet distinguish this year's profit from prior years' once a real fiscal-year boundary matters.
- Reports are not yet filterable by branch in the UI (the backend already accepts a `branch_id` scope internally via `AuthContext`, but no branch selector is exposed on these three screens yet) — consistent with the rest of the Accounting tab today.
- No CSV/PDF export on these three screens yet (Reporting Polish, Milestone 2).
