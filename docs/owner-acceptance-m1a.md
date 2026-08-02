# Owner Acceptance — Milestone 1a (Accounting Standardization)

**Purpose of this document**: let you personally verify, from a browser, that General Ledger, Income Statement, Balance Sheet, Payments, and company-to-company data isolation are real and correct — not just described in a report. Every number below was checked twice: once by an automated test, once by hand in a real browser session, and the two agree.

**How to open the system**: `http://localhost:3000` in any browser.

**Test data**: two throwaway demo companies, created only for this checkpoint (see §"Test data" below for exactly what's in them and how they were made). No real company data was touched to prepare this.

---

## Test A — General Ledger

**Where to go**: log in (see credentials below) → click **Accounting** in the side menu → click the **General Ledger** tab.

**What to click**: in "Select account", choose **1100 — Cash and Bank**. Set the date range from **2026-01-01** to **2026-12-31**. Click **Show ledger**.

**What you should see**: a table with 4 rows, an Opening balance, and a Closing balance:

| Date | Reference | Debit | Credit | Running balance |
|---|---|---|---|---|
| 2026-01-05 | Owner Acceptance Demo — capital injection | 20000.0000 | 0.0000 | 20000.0000 |
| 2026-01-06 | Owner Acceptance Demo — initial inventory purchase | 0.0000 | 4000.0000 | 16000.0000 |
| 2026-01-20 | Owner Acceptance Demo — office rent (operating expense) | 0.0000 | 800.0000 | 15200.0000 |
| 2026-02-10 | PAY-000001 | 1725.0000 | 0.0000 | **16925.0000** |

**Opening balance**: 0.0000. **Closing balance**: **16925.0000**.

**How to know it's correct**: click on "PAY-000001" in the Reference column. It should open a Journal Entry detail page showing the exact two lines that make up that payment — proving the number on this screen isn't just displayed, it's a real transaction you can open and inspect.

---

## Test B — Income Statement

**Where to go**: same **Accounting** page → **Income Statement** tab.

**What to click**: set "From" to **2026-01-01** and "To" to **2026-12-31**. Click **Run report**.

**What you should see**:

| Line | Amount |
|---|---|
| Revenue | **1500.0000** |
| Cost of Goods Sold | (0.0000) |
| Gross Profit | 1500.0000 |
| Operating Expenses | (800.0000) |
| Operating Income | 700.0000 |
| **Net Income** | **700.0000** |

**How to know it's correct**: 1500 Revenue comes from one real sales invoice (3 units × 500 SAR). 800 Operating Expenses is the one office-rent entry visible on the General Ledger in Test A. 1500 − 800 = 700 — the same 700 you can re-derive by hand from the two numbers above it on this exact screen.

---

## Test C — Balance Sheet

**Where to go**: same **Accounting** page → **Balance Sheet** tab.

**What to click**: set "As of" to **2026-12-31**. Click **Run report**.

**What you should see**:

| Assets | | Liabilities | | Equity | |
|---|---|---|---|---|---|
| Cash and Bank | 16925.0000 | VAT Payable | 225.0000 | Owner's Capital | 20000.0000 |
| Accounts Receivable | 0.0000 | | | Current Earnings (unclosed) | 700.0000 |
| Inventory | 4000.0000 | | | | |
| **Total Assets** | **20925.0000** | **Total Liabilities** | **225.0000** | **Total Equity** | **20700.0000** |

**Total Liabilities + Equity**: **20925.0000**

**How to know it's correct**: this is the one number that matters most — **Total Assets (20925.0000) must exactly equal Total Liabilities + Equity (20925.0000)**, and it does, on this real screen, from real transactions, not a fixed demo value. If you post a new transaction (Accounting → Journal Entries → New) and re-run this report, both totals will move together and still match — try it if you want to see the identity hold under a change you make yourself, not one we prepared.

*("Current Earnings (unclosed)" = this year's profit, not yet formally "closed" into Retained Earnings — explained in the Readiness Report below.)*

---

## Test D — Payments

**Where to go**: click **Payments** in the side menu.

**What you should see**: one row — **PAY-000001**, "Customer payment", dated 2026-02-10, **1725.0000 SAR**, with the reference "Owner Acceptance Demo — first payment".

**How to know it's correct**: this is the same payment that appears in Test A's General Ledger and is what brought the invoice's balance to zero. Click **New payment** to see the create screen (you don't need to submit anything — just confirm the screen opens and the customer/invoice pickers work).

---

## Test E — Cross-company isolation

**Where to go**: log out (top-right menu → Log out), then log back in with **Company B**'s credentials (below) instead of Company A's.

**What you should see**: the Dashboard shows **0.00 SAR** everywhere. If you repeat Tests A–D above while logged in as Company B, every screen will be empty — no Journal Entries, no Payments, none of Company A's numbers.

**How to know it's correct**: Company B is a real, separate company that was never given any of Company A's data. What you're seeing isn't "Company B has nothing to show yet" by coincidence — it's the same database-level protection (Row-Level Security) that keeps every company's data separated verified in this session with the real login of Company B, not a developer bypass.

---

## Login credentials (demo/test only — not real accounts)

| Company | Email | Password | Purpose |
|---|---|---|---|
| A — Owner Acceptance Demo Co. | `owner-demo-a@example.com` | `OwnerDemo!2026` | Has the transactions for Tests A–D |
| B — Owner Acceptance Isolation Test Co. | `owner-demo-b@example.com` | `OwnerDemo!2026` | Deliberately empty, for Test E |

---

## Test data — exactly what was created and how

Five real transactions were posted into Company A, entirely through the normal application (the same screens/APIs a real user uses — nothing was inserted directly into the database):

1. Owner capital injection — 20,000 SAR into Cash.
2. Inventory purchase — 4,000 SAR of inventory bought with cash.
3. A real Sales Invoice — 3 units at 500 SAR = 1,500 SAR + 15% VAT (225 SAR) = 1,725 SAR — issued through the same Quotation → Sales Order → Invoice flow a real salesperson would use.
4. Office rent — 800 SAR operating expense.
5. A real Payment — the customer paying the 1,725 SAR invoice in full.

This was produced by `backend/src/scripts/seed_owner_acceptance_m1a.py`, which:
- Logs in through the real API — no direct database writes, no admin/superuser shortcut.
- Is safe to run again: it checks what already exists first and only adds what's missing, so re-running it does not create duplicates or corrupt anything.
- Only ever touches these two specific demo companies — it cannot affect any other company's data.

This is a small, purpose-built script for this one checkpoint — not the larger, ~100-record demo dataset planned for a later milestone (Milestone 3 in `docs/master-execution-plan.md`).
