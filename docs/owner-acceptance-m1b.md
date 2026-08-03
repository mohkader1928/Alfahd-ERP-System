# Owner Acceptance — Milestone 1b (Customer/Vendor Subledgers, AR/AP Aging, Traceability)

**Purpose**: let you personally verify what's described in the checkpoint report, from a browser, with no SQL/Postman/developer tools. Every number below was checked twice — once by an automated test, once by hand in a real browser session — and they agree.

**How to open the system**: `http://localhost:3000`

**Important — why a new login**: Milestone 1a's demo company (`owner-demo-a@example.com`) cannot open these two new screens. This is a real, confirmed system limitation, not a bug in this Milestone: that company's admin account was created before these two new permissions existed, and there is currently no way in the system to add a permission to an already-existing account after the fact (explained simply — every account's access list is decided once, when the account is first set up; there's no "add one more permission" button yet). Rather than hide this or leave the new screens untestable, a fresh login was created specifically so you can try them. This limitation itself is worth knowing about — full detail in `docs/17f-subledgers-and-aging.md` §7.

**Login**: `owner-demo-c2@example.com` / `OwnerDemo!2026`

---

## Test F — Customer Subledger

**Where**: Accounting → **Customer Subledger** tab → select "M1b Demo Customer" → date range `2026-01-01` to `2026-12-31` → **Show subledger**.

**What you should see**: 4 rows, in this order:

| Date | Reference | Debit | Credit | Running balance |
|---|---|---|---|---|
| today | INV-000001 | 460.0000 | 0.0000 | 460.0000 |
| today | INV-000002 | 230.0000 | 0.0000 | 690.0000 |
| today | INV-000003 (credit note) | 0.0000 | 230.0000 | 460.0000 |
| today | PAY-000001 | 0.0000 | 460.0000 | **0.0000** |

Opening balance `0.0000`, Closing balance `0.0000`.

**How to know it's real**: click "INV-000001" — it opens the actual Sales Invoice. Click "PAY-000001" — it opens a real Payment page, which itself shows which invoice it paid and links back to it.

## Test G — Vendor Subledger

**Where**: Accounting → **Vendor Subledger** tab → select "M1b Demo Vendor" → same date range → **Show subledger**.

**What you should see**: 1 row — "BILL-000001", credit `345.0000`, running balance `-345.0000`. Opening `0.0000`, Closing `-345.0000` (this vendor is owed 345 SAR — deliberately left unpaid so it also shows up in Test I).

## Test H — AR Aging

**Where**: Accounting → **AR Aging** tab → **Run report**.

**What you should see**: **no rows at all.** This is correct, not an empty/broken screen — the one invoice that would otherwise appear here (INV-000002) was fully cancelled out by its credit note (Test F), so nothing is actually owed.

## Test I — AP Aging

**Where**: Accounting → **AP Aging** tab → **Run report**.

**What you should see**: 1 row — "M1b Demo Vendor", "BILL-000001", balance `345.0000`, aged into whichever bucket matches how many days have passed since the bill was created (it moves forward automatically as real time passes — that's expected, not a glitch).

## Test J — Drill-down from General Ledger

**Where**: Accounting → **General Ledger** tab → account `1200 — Accounts Receivable` → date range `2026-01-01` to `2026-12-31` → **Show ledger**.

**What you should see**: a new **Source** column next to Reference, showing "Sales Invoice" or "Payment" for each row. Click any reference (e.g. "INV-000001") — it opens the Journal Entry behind it. On that page, look for **Source document** — click it, and it opens the real Sales Invoice that caused that accounting entry in the first place.

This is the full chain, provable in one sitting: **Invoice → Journal Entry → General Ledger → Customer Subledger → Payment**, and back again.

## Test K — Print a Statement

**Where**: Accounting → **Customer Subledger** tab (after running Test F) → **Print statement** button.

**What you should see**: a clean, letterhead-style page (browser print preview) showing the customer's name and the same figures as Test F — this is the same real data, just formatted for printing or saving as a PDF from your browser's own print dialog.

---

## What is not yet Owner Accepted

Nothing above counts as accepted until you've tried it yourself and said so. Testing it does not itself grant acceptance — that's your call to make explicitly.
