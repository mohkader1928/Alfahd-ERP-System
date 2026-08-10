# Project Progress — Master Status Document

**This file is the authoritative, living record of where the ERP system
actually stands.** It is rebuilt from direct repository inspection each
time it's updated — never from memory of prior reports, and never from
what a phase name implies. Every completion percentage below is backed by
a specific file, endpoint, table, or test cited inline; a percentage with
no evidence next to it is a bug in this document, not a fact about the
project.

**Last verified**: 2026-08-10 — **UI/UX: selectable color themes**. Owner
request: a cosmetic change to the app's overall color — two additional,
clearly-labeled, eye-comfortable color options alongside the existing
default, with the end user choosing between them.

Previously the app had exactly one palette (`app/globals.css`'s `:root`/
`.dark`), a fully achromatic shadcn default (every OKLCH color has zero
chroma — literally no hue anywhere except the red `--destructive`), and
only a light/dark toggle (`lib/theme.tsx`, `erp.theme` in localStorage).

Added two full palettes — "أزرق" (Blue, hue ~254) and "أخضر" (Green, hue
~155) — each independently tuned for both light and dark mode (4 new
`:root`/`.dark` variable blocks gated by a `data-color-theme` attribute
on `<html>`, same structure as the existing default). Chroma kept low
(0.1–0.18 on primary/accent, ~0.01–0.02 on background/card) so both read
as calm and readable for long sessions rather than a saturated brand
color — background/foreground/border still carry only a faint tint, the
same "neutral with a slight hue bias toward the accent" principle used
elsewhere in this app's design.

`lib/theme.tsx`'s `ThemeProvider` now also tracks `colorTheme` (persisted
separately as `erp.color-theme`, independent of light/dark). New palette
picker in the Topbar next to the existing light/dark toggle: a palette
icon opens a dropdown listing all three options, each with its own color
swatch, label, and a checkmark on the active one — the same dropdown
pattern already used elsewhere in the Topbar, so it's immediately
recognizable rather than a new interaction to learn.

tsc/eslint/`next build` clean. Live-verified: switching to Blue
recolors `--primary`/`--background` live with no reload; switching to
Green likewise; combining Green with dark mode produces a correctly
dark, green-tinted palette; the checkmark tracks the active selection;
and the choice survives a page reload (localStorage round-trip).

**Immediately prior** — on top of committed `8a3205c` (`main`) —
**UI/UX: Accounting/Inventory sidebar menus + far-away "Apply" button**.
Owner request: list every option in
the Accounting dropdown menu and land directly on the chosen screen
instead of a screen showing all options horizontally, and move the
"Apply" filter button since it required scrolling to reach.

Audit found both complaints share one root cause. `accounting/page.tsx`
is a single page with all 14 reports (Chart of Accounts, Journal
Entries, Fixed Assets ×3, Trial Balance, General Ledger, Income
Statement, Balance Sheet, VAT Summary, Customer/Vendor Subledger, AR/AP
Aging) rendered as one wide `TabsList` row of buttons at the top — but
`lib/nav-config.ts`'s sidebar "Accounting" group only linked to 6 of the
14, so the other 8 were reachable only by landing on the page and
hunting through the wrapped tab-button row, which is also what was
pushing each report's "Apply" button below the fold. Identical pattern
found in Inventory (8 tabs, only 5 in the sidebar).

Fixed both pages the same way: `nav-config.ts` now lists all 14
Accounting links and all 8 Inventory links (every one already has a
working `?tab=` route). `accounting/page.tsx` and `inventory/page.tsx`
no longer render the `TabsList` row at all — since every individual
report already shows its own title (`ReportView`'s `title` prop, checked
across all 22 tab components before removing the outer generic page
heading), landing via any sidebar link now shows only that one screen.
tsc/eslint/`next build` clean. Live-verified: sidebar now lists all 14
Accounting items; opening Vendor Subledger for a partner lands directly
on that report with the Apply button at y≈204px inside a 720px viewport
(no scroll needed, vs. previously being pushed past the fold by the
14-tab row).

**Immediately prior** — on top of committed `f07ee76` (`main`) — **Bug
fix: vendor/customer subledger and GL deep-links stuck on the first
partner/account viewed**. Owner report:
registering a purchase order (PO-000033, real vendor "شركة القارات
الخمسة") and then checking a *different* vendor's account only ever
showed "القارات الخمسة"'s movements — asked for the root cause, a fix,
and prevention of recurrence anywhere else in the system.

Root cause confirmed NOT a data bug: `purchase_order.partner_id` and
`vendor_bill.partner_id` for PO-000033 and every other PO in that company
were checked directly in the database and are all correct and distinct
per vendor. The bug is in `frontend/app/(dashboard)/accounting/page.tsx`:
`CustomerSubledgerTab`, `VendorSubledgerTab`, and `GeneralLedgerTab` (plus
`FixedAssetCardTab` in `features/fixed-assets/components/`) each seed
their selected partner/account from a `?partner=`/`?account=` deep-link
query param using a lazy `useState(initialX ?? "")` initializer — which
only runs on the component's *first* mount. Clicking "View vendor
account" from one Partner Profile, then from a different Partner
Profile's page, lands on the same `/accounting?tab=vendor-subledger`
route both times with only the query param differing; since the
component was already mounted from the first visit (Next.js App Router
does not remount a page/tab just because search params changed, and can
even revive an already-rendered instance from its client-side Router
Cache after an intervening navigation to a different route), the second
deep-link's new partner id was silently ignored and the report kept
showing the first vendor's data under the second vendor's name — an
honest, undetectable-to-the-user misattribution, not a crash.

Fixed all 4 occurrences with the same pattern already used successfully
in this session (compare the incoming prop against what was last synced,
re-set state during render if it changed — not a `useEffect`, matching
the `react-hooks/set-state-in-effect` rule already enforced in this
repo). A repo-wide grep for the same `useState(initial\w+Id ?? ...)`
shape confirmed these were the only 4 instances. tsc/eslint/`next build`
all clean. Live-verified in the browser: opened Vendor A's subledger
(correct), navigated away and into Vendor B's Partner Profile, clicked
"View vendor account" again — now correctly shows Vendor B's own
movements instead of Vendor A's.

**Immediately prior** — on top of committed `baabb64` (`main`) —
**Journal Entry visibility + pre-post editing**. Owner request: "أضف زر... لإظهار القيد المحاسبى الناتج عن
هذه الحركة ودائمًا اسمح بالتعديل على أصل الحركة... وفى حالة الحفظ عدل
بالطبع القيد المحاسبى المقترن" — a "View Journal Entry" button on every
screen whose transaction posts one, and the ability to always edit the
original document, regenerating its journal entry on save.

The edit-and-regenerate-JE part collided with two invariants already
built into this system: `trg_journal_entry_posted_immutable` /
`trg_journal_entry_line_immutable` (migration `461205cf56a6`, FR-ACC-004)
physically block any UPDATE on a posted journal entry at the database
level — correcting one requires reversing it and posting a new one, not
an in-place edit — and a cleared/reported ZATCA Tax Invoice is legally
required to stay immutable, correctable only via a Credit Note (the
mechanism the P0-9 work above just built out). Flagged this conflict to
the Owner before implementing; the Owner chose **edit allowed only
pre-posting** (the option matching the existing architecture, zero
compliance risk) — editing a transaction that already has a posted
journal entry stays impossible by design, correctable only through the
existing reversal-document flow (Credit Note / Debit Note / JE reverse).

**"View Journal Entry" button** — added to Sales Invoice, Vendor Bill,
and Payment detail pages (all three already stored their own
`journal_entry_id`; `SalesInvoiceOut`/`VendorBillOut` didn't expose it
over the API yet — added). Live-verified: opened a Credit Note's
`journal_entry_id`, landed on the real JE detail page showing its actual
Dr Revenue / Cr AR / Dr VAT lines.

**"Always allow editing pre-post"** — three document types previously
had **no edit endpoint at all**, not even in their own pre-post window:
- `PUT /sales/quotations/{id}` — only while `status='draft'`. New
  `sales/quotations/[id]/edit` page (mirrors the create-page's line
  editor, pre-filled). `GET /sales/quotations/{id}` changed shape from a
  flat `QuotationOut` to `{quotation, lines}` (`QuotationDetailResponse`)
  since there was previously no way to fetch a quotation's own lines at
  all — the quotation detail page now also shows a lines table for the
  first time.
- `PUT /purchasing/orders/{id}` — only while `status='draft'` (safe: every
  line's `qty_received`/`qty_billed` is guaranteed zero until confirmed).
  New `purchasing/orders/[id]/edit` page.
- `PUT /purchasing/vendor-bills/{id}` — only while `status` is
  `matched`/`mismatched` (before `:approve`), standard bills only. A
  **mismatched bill was previously a dead end** — no way to correct a
  wrong qty/price against the PO short of leaving it permanently
  unpostable; this closes that gap. Inline edit directly on the bill
  detail page (its lines are already tied to real PO lines, so a picker
  wasn't needed — just editable qty/price per existing line). Old lines'
  `qty_billed` contribution on their PO line is rolled back before the
  new lines' 3-way match recomputes, reusing `register_bill`'s own match
  logic.

3 new permission codes (`sales.quotation.update`,
`purchasing.order.update`, `purchasing.vendor_bill.update`), granted to
the Sales/Purchasing & Warehouse role templates and (as with every
permission added mid-engagement) automatically included in any newly
bootstrapped company's Admin role; existing companies' Admin role needs
these granted once via Settings → Security (done for the demo company
during verification).

11 new backend tests (draft-quotation/PO edit round-trips, confirmed-
quotation/PO edit correctly rejected, mismatched-bill-corrected-then-
approved, posted-bill edit correctly rejected, invoice/credit-note
`journal_entry_id` exposure). Full suite 368/369 (1 known-flaky,
unrelated inventory-concurrency test, passes in isolation),
ruff/tsc/eslint/`next build` all clean. Live-verified end to end in the
browser: edited a draft quotation's customer/date/line (total recomputed
450.00 SAR from 150.00 SAR) and a draft PO's qty (total recomputed 770.00
SAR from 77.00 SAR), and opened a real Sales Invoice's "View Journal
Entry" button through to its actual GL lines.

**Immediately prior** — on top of committed `6051916` (`main`) — **P0-9
second follow-up: freeform multi-line returns, original document made
optional**. Owner feedback
on the dedicated-screens pass: "المرتجع لا يشترط ان يكون لكامل فاتورة
المبيعات او المشتريات... اطلب منك ان يكون المرتجع لعدة اصناف ليسوا
ضمن فاتورة واحدة مع وضع حقل اختيارى رقم الفاتورة... مع مراعاة معالجة
ضريبة القيمة المضافة بطريقة صحيحة" — a return must not require a
single whole invoice/bill; it must support arbitrary product lines
that were never on one invoice together, with the original-document
reference reduced to an optional traceability field, and VAT computed
correctly per line.

Sales side was schema-feasible immediately (`sales_invoice.
original_invoice_id` and `.sales_order_id` were already nullable).
Purchasing needed a real schema change: `vendor_bill.purchase_order_id`
and `vendor_bill_line.purchase_order_line_id` were both `NOT NULL`
(every debit note previously inherited its PO from the original bill,
and every line 3-way-matched to a real PO line) — migration
`b3c4d5e6f7a8` makes both nullable; standard bills are unaffected,
enforced at the application layer, not the column.

New backend methods, additive alongside the existing single-document
`issue_credit_note`/`issue_debit_note` (both left untouched, still the
right call when returning one whole document):
`SalesInvoiceService.issue_credit_note_for_lines` (partner_id required,
`original_invoice_id` optional, freeform `lines`, same flat-15%-VAT
per-line computation `issue_invoice_from_order` already uses elsewhere
in this codebase) and `VendorBillService.issue_debit_note_for_lines`
(mirror, partner_id required, `original_bill_id` optional). New routes
`POST /sales/invoices:return` and `POST /purchasing/vendor-bills:return`
(collection-level, not nested under an ID, since there may be no single
parent document). Restock: Sales resolves each line's cost from the
original invoice's own delivery move when one is referenced and the
product matches, else falls back to the location's current moving-
average cost (`_restock_for_credit_note_lines`); Purchasing reuses the
existing `_restock_for_debit_note` unchanged — it was already
product/qty-driven via the valuation engine's current cost, never
dependent on an original document.

7 new backend tests (freeform with no original reference computing
VAT correctly, freeform with an optional reference using its own
custom lines instead of a verbatim copy, restock at original-delivery
cost when the product matches vs. average-cost fallback when it
doesn't). Full suite 361/362 (1 known-flaky, unrelated inventory-
concurrency test — passes in isolation), ruff/tsc/eslint/`next build`
all clean. Live-verified end to end in the browser for both modules:
picked a customer/vendor directly (no invoice/bill selected at all),
added a line via the product picker, submitted — real `201 Created`
responses confirmed via network inspection (`credit_note`/`debit_note`
type, `original_invoice_id`/`original_bill_id`/`purchase_order_id` all
`null`, correct per-line VAT: e.g. 150.00 subtotal → 22.50 tax → 172.50
total).

**Immediately prior, same session** — on top of committed `67d05c5`
(`main`) — **P0-9 follow-up: dedicated Sales Return / Purchase Return
screens** (commit `67d05c5`). Owner feedback on the first P0-9 pass: the
restock checkbox added to the Invoice/Bill detail pages'
credit-note/debit-note forms was too buried — "أجد الخيار ضمن قائمة
المبيعات أو المشتريات" (couldn't find the option within the
Sales/Purchasing menu), and asked for it to be named exactly "مرتجع
مبيعات" inside the Sales menu and "مرتجع مشتريات" inside the Purchasing
menu. Added: a new Sales nav entry routing to `/sales/returns` (a list
of every credit note — `invoice_type=credit_note` is already what a
Sales Return is in the data model, no new document type needed) plus
`/sales/returns/new` (originally a single-invoice picker; superseded by
the freeform multi-line editor above); the mirror for Purchasing at
`/purchasing/returns` and `/purchasing/returns/new`. `GET
/sales/invoices` gained an `invoice_type` filter and `GET
/purchasing/vendor-bills` gained a `bill_type` filter so both list
screens ask the server for exactly the return rows server-side, rather
than fetching everything and filtering client-side. 2 backend tests
(server-side type filtering, proving the original document never leaks
into its own returns list). Live-verified end to end: created a return
from the new `/sales/returns/new` screen, confirmed it appeared in the
`/sales/returns` list with the exact Owner-requested Arabic naming, and
produced a real `return` stock move in the Inventory moves list.

**Immediately prior, same session** — on top of committed `3c79e24`
(`main`) — **P0-9: Sales Return + Purchase Return** (commit `3c79e24`), an
Owner-requested addition beyond the original 8-item 3-Day Brief
("اضافة اختيار مرتجع للمبيعات فى موديول المبيعات ومرتجع المشتريات فى
موديول المشتريات"). Audited first: Sales' Credit Note and Purchasing's
Debit Note already existed (from earlier in this engagement) but were
deliberately financial-only — their own docstrings say so explicitly
— reversing AR/Revenue/VAT or AP/GRNI/VAT but never touching
inventory. "مرتجع" (return) in Gulf ERP practice means both the
financial reversal and the physical stock movement, so this extends
both documents with an optional `restock` flag (default `true`) rather
than building a parallel document type from scratch. Sales Credit Note
restocks each line at the *exact* unit_cost its original delivery's
own `StockMove` rows recorded (a lookup, via a new
`StockMoveRepository.list_by_source`/`InventoryValuationService.list_moves_for_source`,
not a recompute from current average/FIFO state, which could have
drifted since the sale) and posts a reversing Dr Inventory / Cr COGS
entry. Purchase Debit Note issues the returned qty back out through
the standard valuation engine — symmetric to any other outgoing move,
since there's no single original layer to reverse the way Sales has —
and posts Dr GRNI / Cr Inventory. A new `return` stock_move type
(migration `f3a4b5c6d7e8`, widening `ck_stock_move_type`) keeps a
restocked return visually distinct from an ordinary receipt/delivery
in the product cardex and stock-moves list. `restock=false` preserves
the exact old financial-only behavior for cases where goods aren't
physically coming back (price corrections, damaged-beyond-resale
goods). Frontend: a "return goods to stock" checkbox, checked by
default, on both the Sales Invoice credit-note form and the Vendor
Bill debit-note form. 8 new backend tests (restock on/off for both
documents, exact cost/qty/GL assertions) plus 2 pre-existing tests
updated for the new default `restock=True` behavior (one already
predicted the exact GRNI figure change in its own comment). Full suite
352/352 across three consecutive runs (the same one pre-existing,
unrelated inventory-concurrency test flaked once and passed cleanly
in isolation each time — confirmed not caused by this work; a
`test_sales_invoice_list_pagination.py` test flaked once under full-
suite load and passed cleanly in isolation too), ruff/tsc/eslint/
`next build` all clean. Live-verified the Sales Return end to end
against the demo company: issued a credit note with the restock
checkbox checked (default), confirmed the resulting `return` stock
move in the Inventory moves list at the original sale's own cost. The
Purchase Return side re-uses the identical, already-fully-tested
pattern (same checkbox component, same backend design) and was
verified via its 6 dedicated backend tests rather than repeating the
live UI walkthrough a second time.

**Immediately prior, same session** — on top of committed `9654140`
(`main`) — **P0-8: Dashboard KPIs + fiscal-year-aware chart** (commit
`9654140`), the 8th and final
item of the 3-Day Brief. `company` had no fiscal-year concept anywhere
in the schema — the Dashboard's "current period" KPIs and trend chart
were hardcoded to a calendar year (Jan 1–Dec 31), and the trend chart
was additionally hardcoded to a fixed 6-month trailing window
disconnected from the KPI cards' own period filter (confirmed by
reading `DashboardService._sales_trend`'s old signature, which ignored
the caller's `period_start`/`period_end` entirely and always used
`date.today()`). Added `company.fiscal_year_start_month` (1–12, default
1 = January — every existing company's behavior is unchanged unless an
Owner deliberately reconfigures it; migration `e2f3a4b5c6d7`), editable
from Settings → Company. The Dashboard now computes the real "fiscal
year to date" range from that field instead of assuming Jan–Dec, and
`_sales_trend` was rewritten to return one point per calendar month
within the *requested* range rather than a fixed count — so the KPI
cards and the trend chart always describe the same period, whatever a
company's fiscal year actually is. Added a 5th KPI, Cash Balance
(account 1100, same `account_balance` mechanism already used for
AR/AP), closing the other half of "KPIs" in the item's own title.
Backend: 4 new tests (cash balance reflects a posted manual JE, trend
length matches the requested range exactly rather than a hardcoded
number, fiscal_year_start_month defaults to 1 and is PATCH-editable);
2 pre-existing dashboard tests updated for the trend's new semantics
(6→12 points for a full-calendar-year request, matching the range
instead of an arbitrary fixed window). Full suite 349/349 (the same
one pre-existing, unrelated inventory-concurrency flake confirmed
passing in isolation again), ruff/tsc/eslint/`next build` clean.
Live-verified end to end against the demo company: changed the fiscal
year start month to April in Settings, watched the Dashboard's period
switch live to "01 Apr 2026 – 31 Mar 2027" with the trend chart
re-labeled Apr→Mar instead of Jan→Dec, then reverted to January to
leave the demo company's state unchanged for other work.

**Immediately prior, same session** — on top of committed `d053aa0` (`main`) —
**P0-7: UI/UX quick high-impact pass** (commit `d053aa0`), the 7th item
of the 3-Day Brief. Re-audited `docs/18-ui-ux-audit.md`'s findings
against current source rather than trusting the document at face
value — it predates several sessions of work — and confirmed most of
its Critical/High items are already resolved: company-selection UI
(B1), Sales Order/Invoice list pages including the `GET /orders`
endpoint the audit flagged as missing (C1/C1b), Purchasing/Inventory
migrated onto `ERPListView` (A1), `<Can>` gating on the previously
ungated Purchasing-approve/Sales-credit-note actions (A5), a toast
system wired into 19 files (A7), and a full Cycle Count UI (D-
Inventory) all exist now where the audit found them missing. Two
genuine gaps remained and were fixed: `GET /reporting/export/sales-invoices`
existed on the backend with zero frontend caller (`grep` for the path
across the whole frontend returned nothing) — wired via `ERPListView`'s
`exportAction` prop, itself already built but unused anywhere in the
app; and `SalesInvoice.sales_order_id`, already returned by the API and
present in the frontend's own type, was never rendered — the Invoice
detail page now links to its originating Sales Order. Frontend-only,
tsc/eslint/`next build` clean, live-verified against the demo company
(seeded, real invoice data): the export button downloads a real CSV
(network request confirmed 200 OK) and the order link navigates to the
correct Sales Order. Remaining audit items not touched in this pass,
left for a future bundle since they were assessed as Medium/Low or
larger-scope than "quick": `zod`/`react-hook-form` schema validation
(installed, still unused), `FormView` adoption on the 2 remaining
hand-rolled forms (`sales/quotations/new`, `purchasing/orders/new`),
and the unsearchable product picker in Inventory's Stock/Transfer forms.

**Immediately prior, same session** — on top of committed `646a0a7` (`main`) —
**P0-6: RBAC audit and completion** (commit `646a0a7`), the 6th item of
the 3-Day Sellable Product brief. Audited via a full read of the
identity module's role/permission model first (join-only RBAC, no
Super Admin bypass, `is_system` a dead column never set or checked)
and found the single highest-severity gap: `backend/tests/test_settings_roles.py`
had two tests that deliberately stripped `company.manage`/`role.manage`
off the bootstrap Admin role to prove `require_permission` enforcement
— proving, as a side effect, that a company could permanently strip
`role.manage` off its only role with zero in-product recovery path.
Fixed by making `is_system` real: `create_role(..., is_system=True)`
is now set on the bootstrap Admin role at both `/bootstrap` and
`/companies`, and `update_role_permissions`/the new rename/delete
routes all reject a system role with 422. The two tests were rewritten
to create a disposable custom role instead of stripping Admin,
preserving their original intent (proving the permission check) without
relying on the now-forbidden action.
Added, from a prioritized subset of the audit's findings (explicitly
deferred: app-wide `<Can>`-gating of page tabs, and
`accounting.reports.*` vs `reporting.*` naming normalization — both
cosmetic, not security-bearing, since the backend enforces regardless):
`PATCH /roles/{id}` (rename) and `DELETE /roles/{id}` (blocked while
any user still holds the role, mirroring P0-4's Chart-of-Accounts
delete guard) — previously only possible via direct DB access; four
default role templates (Accountant, Sales, Purchasing & Warehouse,
Read-Only Viewer — the last derived from `scope=="screen"` in
`PERMISSION_CATALOG` so it can't drift) seeded alongside Admin at both
`/bootstrap` and `/companies` via `UserManagementService.seed_default_role_templates`,
giving real separation-of-duties from day one instead of one
all-powerful login; RLS on `role_permission`/`user_role`
(migration `d1e2f3a4b5c6`) — pure join tables with no `company_id` of
their own, so the policy is an `EXISTS` subquery against
`role.company_id` rather than the usual column-based policy, and they
had `relrowsecurity=false` (no isolation at all) before this; audit
logging for `create_role`, the one role-related action that previously
left no trail (`assign_role`/`remove_role`/`update_role_permissions`
already had one). Frontend: rename/delete buttons and a locked-message
banner on the role detail screen, all permission checkboxes disabled
and the Save button hidden, gated on `role.is_system` — the existing
"System"/"Custom" badge now reflects reality for the first time since
Admin was actually never `is_system=True` before this change.
18 new backend tests (system-role immutability × 3, custom-role
rename/delete success and delete-blocked-by-assignment, default
templates seeded at both bootstrap paths, Read-Only Viewer matches the
full screen-permission catalog, RLS isolation for the two join tables
verified via a direct `AsyncSessionLocal`+`SET LOCAL` query — the same
connection path the API itself uses, not a mock), full suite 346/346
(one pre-existing, unrelated inventory-concurrency test flaked in the
full run and passed cleanly in isolation — confirmed not caused by
this work), ruff/tsc/eslint/`next build` all clean. Live-verified end
to end against a fresh bootstrap company: 5 roles appear with correct
`is_system` flags and permission counts; Admin's permission grid is
fully read-only with the lock message showing; a custom role's rename
took effect immediately in both the detail header and the list;
deleting that same role redirected to the list with it gone.

**Immediately prior, same session** — on top of committed `2c689c0`
(`main`) — **Fixed Asset Card and GL reconciliation** (commit `2c689c0`), an
Owner-requested follow-up to P0-5 — the Owner asked for a per-asset
inquiry "مثل كارت الصنف واستاذ مساعد العملاء والموردين" (like the
Product Cardex and Customer/Vendor Subledger) plus proof that the
asset register always ties to Trial Balance's asset/accumulated-
depreciation/net-book-value figures, echoing the standing "always care
about GL integration" requirement already enforced for AR/AP.
`FixedAssetService.get_asset_card` merges an asset's two movement
sources (its own acquisition/disposal, and its depreciation entries)
into one opening/running/closing ledger tracking three parallel
values — cost, accumulated depreciation, net book value — the same
shape `SubledgerService._build_subledger` already uses for one
balance. `get_reconciliation` groups every asset active as of a
chosen date by the real GL account it points to and compares the
register's own sum against that account's actual posted balance via
the same `account_balance_by_id` General Ledger/Balance Sheet already
use, rather than assuming one hardcoded account pair. Three real bugs
found live during this work, each with its own regression test: (1)
Accumulated Depreciation is credit-normal, so its raw GL balance comes
back negative while the register's total is a positive magnitude —
compared directly, a correct register could never match, fixed with a
per-role sign correction; (2) a depreciation entry's date is
period_month (matching its own JE's entry_date), so sorting a
same-month event list by that raw date put a depreciation entry
*before* the mid-month acquisition it depends on, producing a
negative intermediate net book value — fixed by sorting on the
period's month-end while still displaying period_month; (3) the
reconciliation's register total used each asset's *current*
disposed/active flag instead of its state *as of* the requested date,
wrongly excluding an asset disposed on a future date whose disposal
JE hadn't reached the GL yet either — fixed to compare `disposed_at`
against `as_of_date` directly. Frontend: new "Fixed Asset Card" and
"Fixed Assets Reconciliation" tabs (asset/date-range and as-of-date
selectors respectively, full print/PDF/Excel export via the same
`ReportView` shape every other report tab uses); the register list
gained an active-assets totals summary and each asset code now links
to its card. 6 new backend tests on top of P0-5's 9 (15 total for the
module), full suite 335/335 passed, ruff/tsc/eslint clean.
Live-verified end to end against شركة المحمود's demo company: created
a second asset, ran its depreciation, confirmed the card's
chronological order and running values, and watched the reconciliation
tab go from a false "غير متطابق" to a true "متطابق" as each of the
three bugs above was fixed in turn, checked directly against Trial
Balance throughout.

**Immediately prior, same session** — on top of committed `6c83a84`
(`main`) — **Fixed Assets module: register, straight-line depreciation, disposal**
(commit `6c83a84`), P0-5 of the 3-Day Brief. Entirely new — confirmed
via audit beforehand that no fixed-asset/depreciation code, table, or
COA account existed anywhere in the repo. New `fixed_assets` module
(own migration, models, repos, service, routes under
`/api/v1/fixed-assets`, own `FA-000001` numbering) follows the exact
shape every other document type in this codebase already has:
acquisition, depreciation, and disposal each post their own journal
entry immediately via `JournalEntryService`, not as a draft a user
posts separately. Each asset points at three GL accounts (fixed asset,
accumulated depreciation, depreciation expense) picked from the
existing Chart of Accounts rather than a fixed set. Depreciation is
monthly straight-line, manually triggered ("Run Depreciation for
period") rather than a cron job — this codebase's only scheduled-work
infra (Celery) has no Beat configured anywhere, so adding one was out
of scope for this item; `UNIQUE(fixed_asset_id, period_month)` makes
re-running the same period a safe no-op, and the depreciable base is
capped so the final period never over-depreciates past
`cost - salvage_value`. Disposal writes off the asset at net book
value (derived from posted depreciation entries, never a stored
figure) and recognizes the resulting gain or loss into a caller-chosen
P&L account. Seeded the missing Fixed Assets/Accumulated
Depreciation/Depreciation Expense/Gain-Loss-on-Disposal accounts into
`DEFAULT_SAUDI_COA` for new companies, and backfilled the same into
every already-onboarded company's CoA (skipped where a company already
had its own account at that code) so the screen is usable without a
manual setup step. Two real bugs found and fixed during this work: (1)
the create/dispose routes queried the DB again after `db.commit()` to
build their response, but company context is set via `SET LOCAL`
(transaction-scoped per `session.py`), so the post-commit query ran
with no company context and RLS silently broke — fixed by reading the
response before commit; (2) `run_depreciation` compared an asset's raw
`acquisition_date` against the requested period's month-start, which
excluded every asset from its own acquisition month unless bought
exactly on day 1 — found live testing an asset acquired 2026-08-09
against `period_month=2026-08-01` — fixed to compare month-starts
(full-month convention), with a regression test covering both the
newly-eligible and still-correctly-excluded cases. 9 new backend
tests, full suite 329/329 passed, ruff/tsc/eslint clean. Live-verified
in the browser against شركة المحمود's demo company end to end: created
an asset, ran depreciation, disposed it at a loss, and confirmed via
Trial Balance that every GL account involved (fixed asset, accumulated
depreciation, depreciation expense, funding account, loss account)
moved by the exact expected amount with the ledger staying in balance
throughout.

**Immediately prior, same session** — on top of committed `2a659d3` (`main`) —
**Detail-level rollup for Trial Balance / Income Statement / Balance
Sheet** (commit `2a659d3`), an Owner-requested follow-up to the Chart
of Accounts hierarchy work — not one of the 8 P0 items. Lets a user
pick a detail level (1-4) on any of the three account-tree reports and
have sub-accounts deeper than that level collapse into their ancestor,
instead of always listing every leaf account. `ReportingService`
gained `_rollup_ancestor` (walks a row's account up its parent chain
to the target level) and `_rollup_rows` (groups/sums rows by that
ancestor, generic across the three reports' different row shapes via
a `sum_fields` tuple), reused unchanged by `trial_balance`,
`income_statement`, and `balance_sheet`. Section/report totals
(`revenue_total`, `assets_total`, etc.) are untouched by rollup since
they're independent sums, not derived from the row list — confirmed
by test. Fixed a real gap while wiring this in: the trial-balance
route was building `ReportingService(entry_repo)` without the account
repo, which would have made rollup silently a no-op on that one
endpoint specifically. Frontend: shared `DetailLevelSelect` wired into
all three report tabs; the General Ledger drill-down link is disabled
whenever a rollup level is active, since a rolled-up row's account_id
is its own (non-postable) group-account ancestor, whose GL would be
empty. 4 new backend tests (rollup at levels 1 and 2, revenue/expense
rollup, balance-sheet identity holds after rollup); full suite
320/320 passed, ruff/tsc/eslint clean. Live-verified all three tabs
against شركة المحمود demo data: trial balance rolled Cash and Bank's
children into "1100", level-1 rollup collapsed Assets/Liabilities/
Equity/Revenue/Expenses correctly with unchanged grand totals, income
statement and balance sheet rollups preserved gross profit/net income/
the assets = liabilities + equity identity, and drill-down links
disappeared from the DOM at every non-full detail level while staying
present at full detail. Also confirmed (not a bug): several manually
created Arabic-named expense accounts (5300-5900) have no parent set
in this company's data, so they legitimately stay at level 1 rather
than rolling into "5000 Expenses" — a data-structure fact, not a
rollup defect.

**Immediately prior, same session** — on top of committed `95e8fbd`
(`main`) — **Chart of Accounts 4-level hierarchy enforcement** (commit
`95e8fbd`), P0-4 of the 3-Day Brief. The Chart of Accounts had never had update or
delete at all before this — only create — so this bundle added the
missing CRUD alongside the hierarchy rules themselves. New `level`
(auto-computed from parent, capped at 4, backfilled via a recursive
walk rather than assuming the seeded 2-level depth) and `is_group`
(header/category accounts that can't be posted to directly, backfilled
from the data itself — any account referenced as another's parent_id —
which correctly identified the 5 top-level Saudi CoA categories with
no hardcoded list). `create_account` now validates the parent and
auto-promotes it to `is_group=True` the moment it gains its first
child, matching the "auto-compute" spirit of `level` itself rather
than leaving that invariant to the caller. New `update_account`
recomputes level across an entire moved subtree on reparent, rejects
a move that would push any descendant past level 4, rejects moving an
account under its own descendant (cycle guard), and rejects clearing
`is_group` on an account that still has children. New `delete_account`
(soft-delete) is rejected if the account has children or any posted
journal entry lines. `JournalEntryService.create_draft_entry` now
rejects posting to a group account — the one enforcement point the
brief specifically called out. Frontend: parent-account selector
(indented by level), group-account checkbox, level/group-status
columns, and Edit/Delete actions the screen never had before; the
Journal Entry line account picker now filters out group accounts
client-side. 11 new backend tests, 316/316 backend tests pass,
ruff/tsc/eslint clean. Live-verified in the browser: created a level-3
account under "1100 Cash and Bank", confirmed it auto-promoted to a
group account, and confirmed the Journal Entry account picker
correctly excluded all 6 resulting group accounts.

**Immediately prior, same session** — on top of committed `6af06b2`
(`main`) — **Split customer receipts / vendor payments by module and number
sequence** (commit `6af06b2`), a standing Owner directive ("من الآن
ارجو فصل القبض من العملاء عن الدفع للموردين") — not part of the 8 P0
items, given priority over continuing to P0-4 since it's foundational
enough that every payment created afterward should already follow it.
Confirmed with the Owner beforehand that this is an interface-only
split (same `Payment`/`PaymentAllocation` tables, same
`record_payment`/subledger/aging/report logic), not a table-per-type
rebuild. Migration `e1f2a3b4c5d6` backfills every existing payment's
number to a per-(company, payment_type) scheme — `RCT-000001...` for
customer receipts, `PAY-000001...` for vendor payments (same prefix,
now scoped only to vendor payments instead of a shared counter that
left gaps in either series wherever the other type fell in between).
New `PaymentListView`/`PaymentFormView` shared components
(`frontend/features/payments/components/`) parameterized by
`paymentType`/`fixedType` so `/sales/receipts`, `/purchasing/payments`,
and the original `/payments` (kept for the Dashboard's still-generic
quick action) don't each reimplement the same query/columns/form
wiring. Sidebar nav: customer receipts moved under Sales, vendor
payments moved under Purchasing, replacing the old flat "Payments"
entry. 305/305 backend tests pass, ruff/tsc/eslint clean. Live-
verified against real data: both new lists show gap-free type-scoped
numbering, the shared detail page still opens from either list, the
new-receipt form correctly hides the type selector.

**Immediately prior, same session** — on top of committed `8311426`
(`main`) — **Purchases by Supplier report** (commit `8311426`), P0-3 of the 3-Day
Brief, mirroring Sales by Customer (vendor, invoice count, amount/VAT/
total, running AP balance matching Trial Balance) plus an Adjustments
column the brief explicitly asked for beyond the sales-side reference
(debit notes issued in the period, shown separately rather than
silently excluded) and Net Purchases. New `PurchaseReportingService
.by_vendor`, `GET /reporting/purchasing/by-supplier` (date range,
optional supplier filter, PDF/Excel export via the same shared
`ReportTable` framework every other report uses), new
`reporting.purchasing.view` permission, and
`frontend/app/(dashboard)/purchasing/reports/page.tsx` with the
supplier name deep-linking to the existing vendor subledger page for
drill-down/GL reconciliation. Purchasing's sidebar nav converted from
a flat link to a group (Orders & Bills / Reports), matching Sales'
shape. 7 new backend tests including one asserting the report's AP
balance reconciles exactly against Trial Balance account 2100.
305/305 backend tests pass, ruff/tsc/eslint clean. Live-verified
against real data: an existing debit note correctly showed as a
575.00 SAR adjustment reducing that vendor's net purchases to zero.

**Immediately prior, same session — unallocated-payment Subledger fix**
(commit `8af6414`), found live-testing this report against شركة
المحمود's real data, not part of the P0 list but a genuine system-
integrity gap the Owner flagged directly ("هذه مشكلة كبيرة جدا"): a
real, posted customer payment recorded fully on-account (no invoice
picked, e.g. an advance) was completely invisible in that customer's
account statement, overstating their balance by the payment's full
amount (confirmed directly against production: a 100,000 SAR payment,
PAY-000005, was missing). Root cause: `list_allocations_for_partner`
INNER JOINs `Payment` to `PaymentAllocation`, so a payment with zero
(or a partially-unallocated remainder of) allocation rows never
produced a movement — even though `record_payment` already treats an
unallocated remainder as a valid on-account credit, not an error, and
the Sales-by-Customer/Purchases-by-Supplier reports' own payment
totals (summed directly from `Payment.amount`, not via allocations)
already counted it correctly; only the Subledger's own movement list
had this gap. Added `list_unallocated_payments_for_partner` (LEFT
JOIN, remainder = amount − SUM(allocated)), wired into both
`customer_subledger`/`vendor_subledger`. 2 new regression tests
(fully-unallocated customer payment, partially-allocated vendor
payment).

**Immediately prior, same session** — on top of committed `74921a2`
(`main`) — **Vendor Debit Note: P0-2 audit** (commit `74921a2`), the second of the
8 P0 items from the 3-Day Brief. Audited the existing bundle (commit
`24ef1b9`) against the full checklist — accounting direction, supplier
balance, payable impact, GL entries, invoice linkage, permissions,
cancellation/reversal, audit trail — using Sales Credit Note as the
architectural reference, item by item. Most of it checked out exactly:
GL reversal lines are the precise opposite of the bill's own posting,
AP aging (`ap_aging`) and vendor subledger already net a debit note
against its original bill instead of aging it as its own open item,
permissions/linkage already mirror the sales side. Two items that
looked like potential gaps turned out to be non-gaps by symmetry:
Sales Credit Note itself has no cancellation/reversal path (corrected
by issuing another document, not by un-issuing itself) and no
`AuditLogRepository` call either — so the debit note matching that
exactly is correct, not incomplete. Two *real* gaps found and fixed:
(1) the debit-note endpoint was missing the Idempotency-Key protection
docs/16b calls MUST-priority for this exact endpoint shape (a second
debit note against the same bill is legitimate, so it can't be closed
by a status guard — a double-click could double-post the GL reversal);
wired the same shared `begin_idempotent_request` mechanism sales'
credit-note endpoint already uses. (2) the vendor bills list had no
way to tell a debit note apart from a standard bill at a glance (sales
invoices list already shows `invoice_type`) — added a Type column with
an amber warning badge. New
`backend/tests/test_vendor_debit_note_idempotency.py` (5 tests,
mirroring `test_credit_note_idempotency.py`). 296/296 backend tests
pass, ruff/tsc/eslint clean. Live-verified the new Type column in the
real UI: existing debit note (`BILL-000020`) now shows "إشعار مدين"
with the amber badge; standard bills show "فاتورة عادية". No purchase
report exists yet to verify debit-note netting against (that's P0-3,
next) — flagged for P0-3 to handle correctly when built, not treated
as a P0-2 gap since the report itself doesn't exist yet.

**Immediately prior, same session** — on top of committed `991029b` (`main`) —
**Purchase Order partial receipt: data-driven status + auto-billing
redesign** (commit `991029b`), a direct Owner correction of the first
P0-1 cut (commit `e8dc57e`, below) from the 3-Day Sellable Product
Execution Brief (8 P0 items, one bundle at a time, pausing after each
for the Owner's own review/testing — not the continuous-execution
mode). The Owner rejected the first version as not best practice:
status stayed `confirmed` through a partial receipt (should honestly
reflect the data), and billing was a separate manual step (should
auto-fire per receipt). Two clarifying questions were asked and
answered before redesigning: billing is automatic after every receipt,
and full natural completion still auto-closes to `done` (unchanged).
Migration `d0e1f2a3b4c5` adds a `partially_received` PO status.
`record_receipt` now derives status from the actual line data every
time (`confirmed` → `partially_received` the moment any qty is left
outstanding → `done` once everything's in) instead of a receipt just
being logged against a status that never moves, and auto-registers a
vendor bill for exactly the qty just received via
`GoodsReceiptService` → `VendorBillService` (two receipts on one order
now produce two separate bills, each at the PO's own price — verified
live: 92.00 SAR + 138.00 SAR = the 200.00 SAR PO total).
`reopen_purchase_order_line` now restores `partially_received` (not
unconditionally `confirmed`) when the line already has `qty_received >
0`, the same honesty rule applied consistently. The standalone
short-close button was initially removed in favor of the post-receipt
dialog as sole entry point, then the Owner flagged that as a gap of
its own — closing the remaining qty needs to be available at any time,
not only in the seconds right after a receipt — so a persistent
"Close remaining quantity" button was added back (deliberately
different wording from the dialog's own confirm button, to avoid
repeating an earlier same-text duplicate-button bug). Status badges
gained a proper amber `warning` Badge variant (was silently falling
into the same grey `secondary` bucket as `draft`) with larger type on
the order header; the order-list status filter/list was also missing
two of the seven real PO statuses (`partially_received`, `closed`) —
fixed in the same pass. `backend/tests/test_purchase_order_short_close.py`
assertions updated for the corrected transitions. 291/291 backend
tests pass, ruff/tsc/eslint clean. Verified live end-to-end through
the real UI on two separate orders: partial receipt (4/10) →
`partially_received` + auto-bill for the 4 → "receive later" closes
the dialog with no side effect (status unchanged) → received the
remaining 6 → second auto-bill for the 6 → auto-closed to `done`; on a
second order, partial receipt (6/10) → short-closed via the *standalone*
button (not just the auto-popup) → `closed` → reopened → correctly
`partially_received` (not `confirmed`, since 6 units were already in).

**Superseded — first P0-1 cut** (commit `e8dc57e`): real partial
receipt already worked at the data layer
(`purchase_order_line.qty_received` already accumulated correctly
across multiple goods receipts, over-receipt already blocked); this
bundle added `purchase_order_line.short_closed` and the `closed`
status (migration `c9d0e1f2a3b4`, still valid and unchanged), plus
`short_close_purchase_order`/`reopen_purchase_order_line`. The
underlying schema and short-close/reopen actions from this commit are
still in use — only the status-transition and billing *behavior*
around them changed in `991029b` above.

**Immediately prior, same session — Vendor Debit Note** (commit
`24ef1b9`), a self-selected Product Owner
audit bundle (next-highest-value gap identified after closing out the
Owner's live pricing/accounting requests): Sales already had a Credit
Note (reverses a posted invoice) but Purchasing had no equivalent for
reversing a posted vendor bill (goods returned to a vendor, or a price
correction) — a real asymmetry against SAP B1/Dynamics 365 BC/Odoo.
Added `vendor_bill.bill_type`/`original_bill_id` (migration
`b8c9d0e1f2a3`, mirroring `sales_invoice.invoice_type`/
`original_invoice_id` exactly — a debit note inherits the original
bill's `purchase_order_id` and each line's `purchase_order_line_id`
rather than needing a PO of its own, same as how a sales credit note
needs no sales order of its own), `VendorBillService.issue_debit_note`
(full reversal only — Dr AP / Cr GRNI / Cr input VAT, the exact
opposite of the bill's own posting lines, mirroring the same
COGS/Inventory-untouched simplification the sales Credit Note already
makes), a new `purchasing.vendor_bill.debit_note` permission
(auto-granted to every existing company's Admin role via the startup
sync — no backfill migration needed), and AP Aging / the vendor
subledger updated to treat a debit note exactly like AR Aging already
treats a sales credit note (reduces the original bill's balance,
never its own open AP item). 285/285 backend tests (4 new), ruff
clean, tsc/eslint clean. Verified live end-to-end through the real UI:
built a full procure-to-pay cycle (PO → receipt → bill → approve,
575.00 SAR), issued a debit note against it, confirmed the original
bill dropped out of AP Aging entirely and the debit note itself never
appeared as its own open AP row.

**Immediately prior, same session — backfilled
`product.last_purchase_price` from existing purchase order
history** (commit `aa2c8b3`). Owner-reported follow-up to the pricing-
defaults bundle below: a real product with plenty of purchase history
still showed no default price on a new Purchase Order line, because
`last_purchase_price` only ever gets set going forward from a new PO
line onward — it was never backfilled from purchase orders that
already existed before that migration landed, so every product in a
company with real pre-existing purchase history (like شركة المحمود)
stayed NULL until someone happened to buy it again after the deploy.
The first backfill attempt (same session) silently updated almost
nothing: `product`/`purchase_order`/`purchase_order_line` all carry
FORCE ROW LEVEL SECURITY, and Alembic's `erp_migrate` role is
deliberately NOBYPASSRLS — the exact same silent-no-op trap already
documented in migration `d3e4f5a6b7c8`. Fixed by temporarily lifting
FORCE ROW LEVEL SECURITY for the duration of the backfill (owner-only
DDL — `erp_migrate` owns all three tables) and restoring it
immediately after, mirroring the pattern migration `8957d3c39d54`
already established. Verified live: re-ran via the correct `migrate`
service (erp_migrate role — the `api` container's `erp_app` role
correctly failed with `InsufficientPrivilege`, caught before being
mistaken for success); confirmed every one of شركة المحمود's products
with purchase history now carries the correct `last_purchase_price`,
and confirmed FORCE ROW LEVEL SECURITY is restored afterward. 281/281
backend tests, ruff clean.

**Immediately prior, same session — a batch of Owner-requested pricing
defaults and accounting/reporting
fixes** (commits `7c69f58`, `161d5c1`), submitted directly by the Owner
as one list of five items while live-testing شركة المحمود:

- **Pricing defaults** (`7c69f58`): Purchase Order lines now default to
  `product.last_purchase_price` (updated whenever a new PO line is
  created for that product) instead of starting at 0; Sales Quotation
  lines now default to `product.sales_price` when a product is picked
  (previously always started at 0 — a real, unwired gap); the product
  master gained two new optional reference prices, `price_high` and
  `price_low`, alongside the existing `sales_price` (kept as the
  medium/default tier) — matching the tiered price-list pattern in SAP
  B1/Odoo. Migration `e5f6a7b8c9d0`.
- **Journal entry description** (`161d5c1`): `JournalEntry` gained a
  header-level `description` field (migration `f6a7b8c9d0e1`) —
  previously only line-level descriptions existed, with no way to
  record what a manual entry as a whole was for. Verified live
  end-to-end via the API and the entry detail page.
- **AR/AP Aging total rows** (`161d5c1`): the Owner reported Accounts
  Receivable/Payable in the Trial Balance not matching customer/vendor
  balances. Investigated directly against شركة المحمود's real ledger
  using the Owner's own numbers pasted live into chat — both
  reconcile exactly (AR: 7,770,435.00 in both places; AP: 182,300.00
  in both places). The actual gap was that AR/AP Aging never showed a
  total to compare against the Trial Balance with — added. Also
  surfaced as a process note (not a bug): 10 of شركة المحمود's 16
  vendor bills (4,020,400 SAR) are matched but not yet posted, so
  they don't appear in Accounts Payable yet.
- **Sales by Customer: payments + balance** (`161d5c1`): this report
  previously showed period sales only, which the Owner was directly
  comparing against the Trial Balance's cumulative AR figure and
  finding a mismatch (8,135,330 gross invoiced vs. 7,770,435 net
  balance — the difference being exactly the 364,895 in payments
  received, confirmed live with the Owner). Added
  `payments_received` and a cumulative `balance` column per customer
  so this reconciliation is visible directly in the Sales report,
  without needing to cross into Accounting.

281/281 backend tests, ruff clean, tsc/eslint clean, all four features
verified live (last-purchase-price default, quotation price default,
journal entry description round-trip, Sales-by-Customer totals
reconciling against the Owner's own real numbers).

**Immediately prior, same session — low-stock/reorder-point alerts**
(commit `c21d6ce`), a Product Owner
audit finding: "what's below reorder point right now?" is table-stakes
in every reference ERP (SAP B1, Dynamics 365 BC, Odoo) and was entirely
absent — no `reorder_point` on the product master, no low-stock query,
no proactive alert; a stockout was only discoverable by manually
checking every product's on-hand balance one at a time. Added an opt-in
`product.reorder_point`, a `GET /inventory/stock/low-stock` endpoint
(every product at or below threshold, summed across all
warehouses/locations, with its shortfall), a one-time `low_stock`
notification fired exactly when a sale crosses a product from above to
at-or-below threshold (reusing the existing Notifications module and
`RoleRepository.list_user_ids_with_permission` targeting, the same
pattern already established for PO approvals), and a new "نواقص
المخزون" (Low Stock) tab on the Inventory page. Fixed a real bug found
while building this: the crossing check's aggregate SELECT couldn't see
the same transaction's in-memory `qty_on_hand` decrement because
`AsyncSessionLocal` is configured `autoflush=False` — fixed with an
explicit `session.flush()`. 281/281 backend tests, ruff clean, tsc/eslint
clean, verified live end-to-end (set a real product's reorder_point
above its actual stock, confirmed it appeared on the Low Stock tab with
the correct shortfall, reverted the test value afterward).

**Immediately prior, same session — WEBP images served with the wrong
Content-Type, silently failing to display** (commit `09069b2`), reported
directly by the Owner while
testing (شركة المحمود: uploaded a photo for customer "Awtad Elfahd
Contracting", got the upload-success toast, but the photo never
displayed anywhere — no error surfaced). Traced live: DB row and on-disk
file were both correct, but a direct fetch of the media URL showed
`Content-Type: application/octet-stream` instead of `image/webp` (a
`.png` at a similar path correctly returned `image/png`). Root cause:
Starlette's `StaticFiles` mount at `/media` resolves Content-Type via
Python's stdlib `mimetypes.guess_type()`, which does not reliably have
`.webp` registered across OS/Python builds — and browsers silently
refuse to render an `<img>` whose Content-Type isn't `image/*`, so
nothing in the app's own code ever had a chance to surface the failure.
Fixed by explicitly registering `mimetypes.add_type("image/webp",
".webp")` at startup. Also fixed the actual test-coverage gap that let
this ship: `test_upload_and_delete_partner_image` already uploaded and
fetched back a `.webp` file but only checked `status_code == 200`, never
the `Content-Type` header — added the missing assertion. 281/281 backend
tests, ruff clean, verified live against the exact already-broken file.

**Immediately prior, same session — ZATCA ICV sequencing race closed**
(commit `eab2f10`): the last open finding from the docs/16b concurrency
audit. Two concurrent invoice issuances for the same company (different
orders) could read the same hash-chain tail and compute the same next
ICV, breaking the chain's required total order — fixed by locking the
company row as a serialization anchor. Also fixed a real bug found while
testing: `issue_invoice_from_order`'s error handler mislabeled an
invoice-number collision between two different orders as "already
invoiced" — now distinguishes by constraint name and reports the
accurate, retryable error. 278/278 backend tests, ruff clean.

Also this session: a live production-usage report from the Owner ("This
page could not be found — 404" on `/master-data/vendors` and
`/master-data/customers`) turned out to be a stale frontend dev-server
process that hadn't picked up routes already present on disk — confirmed
by a raw fetch returning Next.js's own built-in 404 shell with HTTP 200,
proving the server's own route table was stale, not a missing/broken
route. Fixed by restarting the dev server; not a code defect and
structurally cannot occur in a production build (which compiles a fixed
route manifest once, with no long-running incremental cache to go
stale).

**Immediately prior, same session — Idempotency-Key mechanism, applied
to credit note issuance** (commit `c937a7a`): the one MUST-priority
endpoint from docs/16b that genuinely needed the full mechanism (not the
simpler status-guard pattern already closing invoice issuance) — a
second credit note against the same invoice can be legitimate, so
blocking retries outright would be a regression, not a fix. New
`shared/idempotency/` module (model, repository, service), opt-in
`Idempotency-Key` header, fully backward compatible. 276/276 backend
tests, ruff clean, 5 new tests including a genuine concurrent-identical-
request test. Verified live against the running dev server.

**Immediately prior, same session — document-numbering races now
return a clean error instead of a raw 500** (commit `3d5c913`): every
numbered document already had `UNIQUE(company_id, number)` as the real
duplicate-prevention guarantee, but only sales invoice issuance
translated the resulting `IntegrityError` into a clean 422 — quotation,
sales order, purchase order, goods receipt, vendor bill, and payment
creation all let it bubble up as an unhandled 500 under real concurrent
creation. Wrapped all 6 remaining paths the same way. 271/271 backend
tests, ruff clean, 3 new concurrent tests (6 simultaneous creates per
document type) assert
no request ever 500s and every created document has a unique number.

**Immediately prior, same session — concurrency-correctness bundle**
(commit `2ec4865`): closed the stock_quant lost-update race and the
purchase_order_line qty_received/qty_billed race with row-level
`SELECT ... FOR UPDATE` locks (docs/16b findings #2/#4), plus added the
one missing `UNIQUE(company_id, number)` constraint on `goods_receipt`
(finding #5). 268/268 backend tests, ruff clean, 3 new genuine-
concurrency tests (`asyncio.gather` over real simultaneous HTTP
requests).

**Immediately prior, same session — sales invoice date forced to today**
(commit `8239919`), a second Owner-reported issue on the heels of the
order-date fix above: `issue_invoice_from_order` forced
`invoice_date = date.today()` on the mistaken assumption ZATCA's
IssueDate required it — it doesn't; `_run_zatca_pipeline` already
generates its own independent `now_iso()` timestamp, fully decoupled
from this field. The Owner directly rejected the "this is intentional"
explanation ("هذا خطأ") after seeing SO-000020 (order_date 2026-01-01)
produce an invoice dated today with no way to override it — correctly,
since the field serves no compliance purpose. Now inherits the order's
own date. 268/268 backend tests, ruff clean, verified live end-to-end
(a fresh 2026-02-14 quotation → order → invoice produced an invoice
dated 2026-02-14, not today).

**Immediately prior — sales order date silently reset to today**
(commit `63033b5`), reported directly by the Owner while testing (a
Sales Order they dated 2026-01-01, SO-000012, never showed up anywhere
dated January). Root cause: `confirm_to_sales_order()` stamped
`date.today()` instead of carrying the quotation's own date forward.
Fixed, plus `invoice_date` was found completely absent from the API
response schema — added and surfaced on the invoice list/detail
screens. 265/265 backend tests, `ruff`/`tsc`/`eslint` clean, verified
live via direct API calls (a fresh January-dated quotation now confirms
into an order that keeps
`order_date: "2026-01-20"` instead of today).

**Also same session**: the Dashboard's sales trend chart was reported as
visually unclear — traced to a real CSS bug (`items-end` on the chart's
row left every bar column's height indefinite, so every bar's `height: X%`
resolved to 0px regardless of the underlying data) plus an unthemed
chart color (`bg-primary`, a chroma-0 grayscale token). Fixed with a
pixel-based bar height and the dataviz skill's validated sequential blue
(`#2a78d6`/`#3987e5`, checked against this app's actual card surfaces).
Commit `f5d83b0`.

**Prior, same day/session, continuous execution per Owner directive**
(see each dated entry below for full detail): `a20ebbf` — Sales Invoices
list pagination; `08369aa` — Inventory Valuation
report; `a2e6752` — Dashboard Enrichment; `3a6f46e` — Document Delivery
(Sales Invoice PDF + Send by Email); `5b88f0f` — Purchase Order Approval
Workflow + Notifications; `ef822dd` — VAT/Tax Summary Report; `a8d3ed3`
— Global Search; `dc94a9a` — Attachments; `7c3adb2` — Users Management
(Identity/Access/Governance); `3138b5c` — Standard Reporting Framework.
Owner Acceptance is pending for the earliest four of these — the
on-screen browser walkthrough specifically remains owed (was blocked on
the Browser preview pane, a tooling/environment issue for that stretch of
the session, not an application bug); every one of those bundles was
instead verified for real through direct authenticated HTTP calls against
live company data plus full automated test coverage, and documented as
such rather than assumed.

**Full-project re-audit (2026-08-07)**: Owner directive to stop
report-by-report execution, review the whole system (backend modules, DB,
frontend, shared components, docs) against Odoo/SAP B1/Dynamics 365 BC/
NetSuite/ERPNext, and re-prioritize. Findings: no Users management UI
exists at all (backend `POST /users`, role/company-access endpoints have
zero frontend — an owner cannot add a second employee without a DB
console); the original Phase 17 blueprint's own §20 recommendation for a
shared `ReportFilter`/export architecture was never built, so all 12
existing reports (at the time) had independently hand-rolled filters,
which is exactly how the Trial Balance Dr/Cr-only regression slipped
through; almost none of the "feels like a real ERP" layer exists (no
global search, notifications, attachments-on-documents, activity
timeline, saved filters, command palette); Audit Log only covers 6 of
dozens of mutating actions; multi-currency is a stored label only (no
`exchange_rate` anywhere in the backend). Reprioritized into 4 bundles
ahead of the original Bundle E report backlog: (1) Standard Reporting
Framework, (2) Identity/Access/Governance (Users UI + audit coverage),
(3) Professional Workspace Layer (search/notifications/attachments/
breadcrumbs/mobile nav), (4) Dashboard 2.0 + remaining reports (Cash
Flow/VAT/Purchasing/Inventory Valuation). Owner approved; execution mode
changed to "audit → implement → test → document → move to next gap
without stopping for a new plan," continuing only for a genuine
architectural decision.

**Historical**: 2026-08-04, on top of committed `5aee470` (`main`) —
**UI/UX Professional pass, Bundle A (first slice — Accounting module),
Owner directive "ERP Professional UI/UX + Functional Completeness"** —
uncommitted at time of writing. Scope of this slice, chosen because the
Owner's own audit request surfaced Accounting as the one module that never
adopted the shared list/report components everyone else already uses:
Chart of Accounts and Journal Entries tabs migrated from hand-rolled
`<Table>` to `ERPListView` (search/sort/pagination/loading/error states,
gained for free); Trial Balance, General Ledger, Income Statement, Balance
Sheet, Customer/Vendor Subledger, AR/AP Aging all migrated to the
previously-built-but-never-used `ReportView` shell, each gaining an
explicit `isError` state it never had; a new shared `ReportPrintHeader`
component (company logo + name + report title + date range) now renders
on every report's print output — before this pass only the two Subledger
tabs had a print header at all; account-creation, JE-creation, and
post/reverse actions gated with `<Can>` for the first time (the whole
1103-line file previously had zero `<Can>` imports); the same
permission-gating gap fixed on 4 more bespoke detail pages (Sales
Quotation confirm, Sales Order invoice-issue, Sales Invoice credit-note,
Purchase Order confirm/receive/bill) that had ungated mutation buttons; AR
Aging rows now drill down to their real Sales Invoice (via the existing
`sourceDocumentHref` map — AP Aging rows still can't, because Vendor Bill
has no detail page yet, a real gap flagged for Bundle C/D, not solved
here); a new shared `lib/format-date.ts` closes the "no date formatter
exists anywhere" gap found by audit, applied so far to Accounting's date
columns only; the Trial Balance's raw `toFixed()` total and the Products
list's unformatted price column were fixed to use the existing
`formatCurrency`. **Implemented, Tested (`tsc`/`eslint`/production build
all clean; zero backend files touched, so the existing 192/192 backend
suite is unaffected), Live Demonstrated**: real browser session confirmed
Chart of Accounts/Journal Entries render on the new list component with
real data; Trial Balance's totals row is genuinely balanced
(361,274.90 SAR both sides against real demo-company data) with a working
print header (company logo confirmed rendered); AR Aging row click opened
the real underlying Sales Invoice detail page; a real bug was found live
(the Trial Balance totals-row label rendered the literal untranslated key
`accounting.tb.total` — a missing i18n entry) and fixed on the spot, then
re-verified. **Owner Accepted: pending — never assumed.** Explicitly
**not** done in this slice, remaining for later passes of the same
directive: the rest of Bundle A (Sales/Purchasing/Inventory list/detail
screens were already largely on the shared components per the audit, but
weren't re-verified this pass; Sales Order/Invoice have **no list page at
all**, a real structural gap the audit found, not yet addressed);
`format-date.ts` rollout beyond Accounting; Bundle B (Employee
photo/Company-logo-everywhere consistency pass — most of the underlying
infrastructure already exists from Entity Media Foundation and just needs
a systematic audit, not new plumbing); Bundle C (Stock Card drill-down,
GL/Trial-Balance-row drill-down beyond what shipped here); Bundle D
(Inventory Count/Stocktake UI — no frontend exists yet despite a
Owner-stated backend workflow, unverified whether that backend workflow
is actually complete); Bundle E (Trial Balance's actual Opening/Period/
Closing column redesign — deliberately deferred so this pass's `ReportView`
shell work isn't re-done); Bundle F (Multi-Currency — explicitly gated on
a short audit first, not started).

**Same-day addendum**: the "Sales Order/Invoice have no list page at all"
gap flagged above was closed in the same pass, since it's a small,
bounded, directly-in-scope fix for item 1's "every module needs a real
list screen" requirement — not deferred. Backend: `GET /sales/orders`
added (`SalesOrderRepository.list_by_company`, reusing the existing
`sales.order.view` permission already gating the single-order endpoint —
no new permission), 1 new test (193/193 backend total, `ruff` clean).
Frontend: `/sales/orders` and `/sales/invoices` list pages built on the
exact same `ERPListView` pattern as Quotations, with a customer-name
resolver (never a raw partner UUID) matching the existing Purchasing
`useVendorLabel`/Inventory `useProductLabel` convention, real
`formatCurrency`/`formatDate`/`statusVariant` throughout, and both added
to the Sales nav group. `tsc`/`eslint`/production build all clean. Live
Demonstrated: both lists render real company data (order/invoice numbers,
real customer names, correctly formatted dates and currency), row links
open the real detail pages, and both render correctly in Arabic
("أوامر البيع" / "فواتير المبيعات" in the nav). **Owner Accepted: pending.**

**Third same-day slice — item 12 (double-click convention) + remaining
raw-date cleanup**: `ERPListView` gained a shared `getRowHref` prop —
whole-row double-click-to-open, Enter-to-open when keyboard-focused, and
a trailing chevron as the discoverability cue (never the *only* way in —
each list's primary column keeps its own `Link` too), per the directive's
explicit "لا تعتمد على double-click وحده... يجب أن يكون هناك visual cue"
requirement. Wired into every `ERPListView` screen with a real detail
page: Quotations, Sales Orders, Sales Invoices, Purchase Orders, Payments,
Journal Entries, Products, and Address Book/Customers/Vendors/Employees
(Vendor Bills and Chart of Accounts intentionally excluded — neither has a
detail page to open). Also closed 3 more raw-date renders the earlier
audit missed (Purchasing Orders, Payments, Sales Quotations), added a
missing Customer column to the Quotations list (previously showed no
customer at all — a real "raw ID/no name" gap), and fixed the Payments
list's Number column, which was plain text with no link to the payment's
own detail page at all (every other list's Number/reference column
already links out — this one silently didn't). `tsc`/`eslint`/production
build all clean. Live Demonstrated: double-clicking a Quotations row
(confirmed via `window.location.pathname` after the click, not just a
visual check) navigated to the real quotation detail page; the chevron
icon and `cursor: pointer` were confirmed present on every row with a
target; the chevron's `rtl:rotate-180` was confirmed actually flipping
(`getComputedStyle(...).rotate === "180deg"` in the Arabic UI — Tailwind
v4 uses the CSS `rotate` property here, not `transform`, which is why a
naive `transform` check would have wrongly read "not applied"). **Owner
Accepted: pending.**

**Bundle A — closing slice (Inventory Moves date/source + inline-form
audit)**: `StockMove` already tracked `moved_at`/`source_table`/`source_id`
on every row (existing ORM columns) but never exposed them — closed by
extending `StockMoveOut` (backend, purely additive, no migration needed)
and adding a Date column (`formatDate`) and a Source column to the
Inventory → Moves tab, reusing the exact same `sourceDocumentHref`/
`sourceDocumentLabelKey` drill-down pattern already proven on GL/
Subledger/AR-Aging: Sales Invoice-sourced moves link to the real invoice,
Goods Receipt/Stock Transfer-sourced moves (no detail page yet) render as
correctly-localized plain-text labels, never a raw `source_table` string.
Separately, a focused audit of Purchasing/Inventory's inline quick-create
mutation surfaces (Warehouse create, Stock Receive, Transfer, Vendor Bill
Approve) against the Owner's 4-point checklist (permission-gated, toast
feedback, drill-down where applicable, no raw IDs/dates/currency) found
zero defects — all four were already built to standard. 193/193 backend
tests, `ruff check src tests` clean, `tsc`/`eslint`/production build all
clean. Live Demonstrated: Moves tab shows real formatted dates
("Aug 03, 2026" / "03 أغسطس 2026" — Western digits enforced in both
locales); a Sales Invoice source link opened the real invoice detail page
(confirmed via `window.location.pathname`); Goods Receipt/Stock Transfer
rows render as "Goods Receipt"/"Stock Transfer" (English) and
"إشعار استلام بضاعة"/"تحويل مخزون" (Arabic) plain text, not raw source-table
strings. **Owner Accepted: pending.**

**Bundle A is now formally closed** (Implemented, Tested, Live
Demonstrated across all 4 slices above; Owner Acceptance still pending as
always — never assumed). Work proceeds directly to **Bundle B — Address
Book + Images** per the Owner's explicit "no stopping between Bundles"
directive.

**Bundle B — audit + first slice**: a full audit of the existing Entity
Media Foundation found it already covers nearly everything the directive
asks for — Company logo (Company Selection, Topbar, Dashboard, every
Accounting print report), Partner image (Customer/Vendor/Employee — all
three are views over the same Partner table, so Employee photo already
works via the same detail page/upload as Customer/Vendor), and Product
image, all already displayed in their List and Detail screens via the
shared `EntityImage`/`EntityImageUpload` components — nothing here needed
rebuilding. The one confirmed, bounded gap: the customer/vendor/product
picker `Select` dropdowns on the Sales Quotation and Purchase Order "new"
forms showed plain text only, no thumbnail — inconsistent with every
other List/Select surface in the app. Closed by adding the same
`EntityImage` (size `xs`) to both the selected-value display and each
option row, in all 4 pickers (Sales Quotation customer/product, Purchase
Order vendor/product) — zero new components, same fallback-to-initials
behavior as everywhere else. No backend changes. `tsc`/`eslint` clean.
Live verification of this slice was blocked by an in-session Browser-pane
rendering issue (compositing failure unrelated to the code change,
confirmed on two separate tabs); DOM inspection before the pane failure
did confirm the dropdown correctly renders an avatar per option. Full
interactive click-through re-verification is still owed and will be
completed opportunistically. **Owner Accepted: pending.**

**Bundle B — closed.** Implemented and Tested (`tsc`/`eslint`/production
build clean, no backend changes); Live Demonstrated via DOM inspection of
the open customer picker on the Sales Quotation form, confirming a real
avatar element renders next to every option, in Arabic — a full
click-to-select + screenshot pass is still owed and will be completed
opportunistically alongside other pending polish. Owner Accepted: pending.

**Bundle C — Traceability**: audit found GL→JE→Source drill-down and
Customer/Vendor Subledger reference links already fully working (existing
`sourceDocumentHref` pattern, Milestone 1b). Two real, bounded gaps closed:
(1) **AP Aging drill-down** — Vendor Bill never had a detail page, so AP
Aging rows showed plain text while AR Aging rows already linked out. Added
`GET /purchasing/vendor-bills/{id}` (reusing the existing
`purchasing.vendor_bill.view` permission and `VendorBillRepository.get_by_id`/
`get_lines` — no new backend mechanism), a new
`/purchasing/bills/[id]` detail page mirroring the existing Purchase Order
detail page exactly (vendor/date/subtotal/tax/total, lines table, gated
Approve action), wired into the double-click convention, and extended
`source-document-links.ts` with a real `vendor_bill` href. AP Aging now
drills down identically to AR Aging. (2) **Stock Card** — Stock Levels had
no per-product move history at all. Added an optional `product_id` filter
to the existing `GET /inventory/stock/moves` endpoint (mirroring the
`partner_id` filter already on vendor-bills list) and a new
`/inventory/stock-card/[productId]` page reusing the exact Stock Moves
tab's column definitions (Date/Type/Qty/Unit cost/Source), wired from a
double-click on any Stock Levels row. 195/195 backend tests (2 new:
vendor bill detail — success + cross-company 404; stock moves product
filter), `ruff` clean, `tsc`/`eslint`/production build all clean. Live
Demonstrated in both languages: double-clicking a Stock Levels row
(confirmed via `window.location.pathname`) opened the correct product's
Stock Card showing only its own 6 moves, with a real Sales Invoice
drill-down link among them; double-clicking a Vendor Bill row opened its
real detail page in both Arabic and English (no raw i18n keys, correct
`formatDate`/`formatCurrency`); AP Aging's BILL-000002 row linked to the
same real detail page. **Owner Accepted: pending.**

**Bundle D — Inventory Operational Completeness**: audit found the
cycle-count/stocktake backend already fully built (create with a real
`system_qty` snapshot, approve posts a balanced GL adjustment entry per
line via the same `InventoryValuationService`/`JournalEntryService`
pipeline every other module uses) but with **zero frontend** — no list,
no detail, no list/detail API endpoints even existed (only create and
approve). Closed by adding `GET /inventory/cycle-counts` and
`GET /inventory/cycle-counts/{id}` (reusing the existing
`inventory.stock.view` permission, no new permission), exposing the
previously-hidden `id`/`stock_move_id` fields on each line, and a new
"Cycle Counts" tab (5th tab, `ERPListView`, double-click convention) plus
`/inventory/cycle-counts/new` (multi-line create form matching the
existing Sales Quotation/PO pattern) and `/inventory/cycle-counts/[id]`
(variance display — counted minus system, color-coded, Approve button
gated by `inventory.cycle_count.manage`). 196/196 backend tests (2 new:
list/detail, cross-company 404), `ruff`/`tsc`/`eslint`/build all clean.
Live Demonstrated end to end, including a real bug caught and fixed live:
the Approve button initially failed with a 400 ("X-Branch-Id header is
required") because the approve endpoint's existing `require_branch=True`
guard wasn't wired through the new frontend client call — fixed by
passing `branchId`, re-verified working (200 OK, status flips to
`approved`). Full chain re-verified real: created a count for A4 Paper
Ream (system 2, counted 5), approved it, confirmed the resulting `+3`
adjustment move now appears on that product's Stock Card (Bundle C) with
Source correctly labeled "Cycle Count", and confirmed the Trial Balance's
account 5200 shows the matching 45.00 SAR (3 × 15.00) GL entry. Verified
in Arabic and English (no raw i18n keys, Western digits enforced). Two
inventory reports named in the original directive (valuation, low-stock)
are deliberately deferred to Bundle E, which already owns "the full
standard-reports expansion across every module" per the Bundle A closure
notes — a low-stock report specifically has no data source yet (no
reorder-point/min-qty field exists anywhere in the schema), so building
it now would mean inventing a new data model outside this bundle's scope.
**Owner Accepted: pending.**

**Out-of-cycle fix (2026-08-04) — no default warehouse recovery**: the
Owner reported a real company ("شركة الفا التجارية") blocked on Purchase
Order goods receipt with "No default warehouse configured for this
company." Root cause, confirmed by code: `is_default` could only ever be
set at warehouse creation time — there was no way to promote an existing
warehouse to default afterward, so any company that created a warehouse
without checking the box (or later needed to switch its default) had no
recovery path except creating a brand-new warehouse. A related, more
serious latent bug was found in the same code path: creating a second
warehouse with `is_default=True` never unset the first, so a company
could silently end up with two default warehouses — the next
default-lookup query (`scalar_one_or_none()`) would then raise instead of
returning cleanly, a real correctness/availability risk, not just this
one company's immediate problem. Fixed both: `POST
/inventory/warehouses/{id}:set-default` (reuses the existing
`inventory.warehouse.manage` permission) now clears any other default for
that company before promoting the target one — the same clearing logic
was also added to warehouse creation, closing the underlying
multi-default bug at its source, not just its symptom. Frontend: a "Set
as default" row action appears on any non-default warehouse in the
Warehouses tab, permission-gated, with toast feedback. 199/199 backend
tests (4 new: single-default-enforced-at-creation regression, set-default
switches correctly and unblocks a real goods-receipt flow end-to-end,
cross-company 404), `ruff`/`tsc`/`eslint`/build clean. Live Demonstrated:
promoted "Secondary Warehouse" to default, confirmed "Main Warehouse"
lost the badge and gained its own "Set as default" button in the same
action, confirmed toast feedback fired, then reverted back to "Main
Warehouse" to leave the demo company unchanged. **Owner Accepted:
pending.**

**Bundle E — Accounting/Reporting Quality, first slice (2026-08-05/07)**:
scope was set by the Owner after direct testing found the shipped Trial
Balance showed Debit/Credit but no Balance — rejected as "not a
professional trial balance." Redesigned per the Owner's explicit spec
(Opening/Period Debit/Period Credit/Closing, with Dr/Cr nature) and built
as the first, reusable slice of the wider Accounting/Reporting Quality
effort (GL/Income Statement/Balance Sheet/Cash Flow/AR-AP/Aging/Statements/
Sales & Purchasing & Inventory reports), not "just add a column":

- **Trial Balance**: `AccountingRepository.trial_balance` now returns
  `opening_balance` (all posted activity strictly before `date_from`,
  computed the same way General Ledger's opening balance already was —
  extended to a grouped-by-account query, not a new mechanism),
  `period_debit`/`period_credit` (same query as before, relabeled),
  `closing_balance` = opening + period net, all signed debit-minus-credit.
  Frontend: 6-column Opening/Period/Closing × Dr/Cr layout, GL drill-down
  link on every account, abnormal-balance highlighting.
- **Real bug caught during this same testing pass and fixed**: the
  closing-balance display logic gated which column showed a number by the
  account's *expected* normal side — so a liability account with a
  genuine net debit balance (e.g. VAT Payable when input VAT from
  purchases exceeds output VAT from sales in the period — confirmed via
  raw SQL on the Owner's real "Almahmoud Trading Co." company: 14,700
  debit vs 10,380 credit) showed **blank in both Dr and Cr columns**,
  silently dropping a real 4,320+ SAR balance from the report and
  breaking the fundamental total-Dr-equals-total-Cr invariant. Fixed by
  always placing the actual signed balance in its true column (Dr if net
  debit, Cr if net credit) regardless of account type, keeping the
  type-mismatch only as a visual flag, not a display gate. Re-verified
  live against real data: VAT Payable's real 51,872.40 SAR closing
  balance now shows correctly, and the grand-total row's Closing Dr and
  Closing Cr now match exactly (1,668,858.78 SAR both sides) — they did
  not before the fix.
- **Second real bug found and fixed in the same pass**: the Trial
  Balance → General Ledger drill-down link updated the URL but silently
  left the visible tab on Trial Balance — because `AccountingPage`'s tab
  state was seeded once from `searchParams` and never re-read on a
  same-route client-side navigation (a hard page reload masked this,
  which is why it wasn't caught earlier). Fixed with the same
  derived-state-during-render pattern already used by `EntityImage`
  (track the last-*observed* URL value, not "does state differ from
  URL" — the naive version would fight a user manually clicking a
  different tab). Live-verified both directions: drill-down now switches
  tabs correctly without a reload, and manual tab-clicking still works
  unaffected.
- **Sales Reports** (`/sales/reports`, new nav entry): By Customer / By
  Product / By Period, backend cross-module queries in a new
  `SalesReportingService` (Reporting module reading Sales+Identity
  directly, the same cross-module-read pattern `DashboardService` already
  used — not a new architecture), reusing `ReportView`/`ReportPrintHeader`.
  New permission `reporting.sales.view`, backfilled to every existing
  Admin role via migration `c1d2e3f4a5b6` (RLS-safe: targets roles
  indirectly through `reporting.dashboard.view`, since `role` has FORCE
  RLS and no company context exists at migration time) and kept in sync
  going forward by a new Admin-role permission-sync step in
  `seed_core_data` (runs at every API startup, `SET LOCAL row_security =
  off`, silently no-ops if the DB user lacks BYPASSRLS).
- **Cycle Count accounting, fixed on Owner request**: stock moves were
  already correctly per-line with a distinct `move_type="adjustment"`
  and `source_table="cycle_count_line"` (confirmed, not changed), but the
  journal entry was posted **once per line** instead of once for the
  whole count. Consolidated into a single net journal entry per cycle
  count (`source_table="cycle_count"`, now with its own GL drill-down
  link straight through to the Cycle Count detail page — closing the
  Report→Account→Entry→Source-Document chain for stocktakes the same way
  it already worked for invoices/bills/payments); a net-zero count (equal
  offsetting increases/decreases) now correctly posts no entry at all
  rather than a meaningless zero-amount one. Stock moves are unaffected
  and still post per line, since physical quantity movements can't be
  netted across different products.
- **Tests**: 2 new Trial Balance tests (opening/period/closing columns
  computed correctly across periods; a liability account's true signed
  closing balance is reported, not clamped), 5 new Sales Reporting tests
  (per-report aggregation correctness, date-range exclusion, permission
  gating), 2 new Cycle Count tests (multi-line net consolidation posts
  exactly one entry sized to the net value; net-zero posts none). 208/208
  backend tests, `ruff`/`tsc`/`eslint`/`next build` all clean.
- **Explicitly not done in this slice** (per the Owner's own "don't
  build everything at once" instruction): GL/Income Statement/Balance
  Sheet/Aging/Statements already had drill-down and print headers from
  Bundle A/M1b and were left alone; Cash Flow, VAT/Tax reporting, and the
  Purchasing/Inventory report sets (valuation, low-stock, purchases-by-
  vendor, etc.) are still open and are the next priority items, not
  silently dropped.

**Owner Accepted: pending.**

**Sales Invoices list: server-side filtering + real pagination
(2026-08-07)**, committed as `a20ebbf`. Fifth bundle picked by the
Product Owner audit methodology — closes the gap the Approval Workflow
bundle's own audit had already flagged as "EXISTS but PARTIAL" (every
list screen loads its full result set client-side; no backend list
endpoint supported `status`/date filters).

- **Real bug found and fixed, not just a missing nice-to-have**:
  `SalesInvoiceRepository.list_by_company` hardcoded `limit=500` with no
  `offset` — any company with more than 500 sales invoices silently lost
  access to older ones in the list screen, permanently, with no filter
  or page control able to reach them. The tell was already sitting in
  the codebase: AR Aging's own call site had to override the cap with
  `limit=5000`, a symptom of the underlying default being wrong, not a
  sign the cap was intentional.
- **Backend**: new `SalesInvoiceRepository.list_by_company_page` — real
  SQL `LIMIT`/`OFFSET` plus a matching `COUNT(*)`, `status`/`date_from`/
  `date_to` filters, and a stable secondary sort key (`id desc` after
  `invoice_date desc`) so paging never skips or duplicates a row when
  two invoices share a date. `GET /sales/invoices` now returns the
  shared `Page[T]` envelope already defined in `shared/api/pagination.py`
  — built in an earlier phase specifically for this and explicitly
  documented there as "not wired into any existing route yet"; this
  bundle is the first to actually use it, establishing the pattern for
  every future paginated list endpoint to reuse rather than re-invent.
  The old `list_by_company` (bare list, no filters) was left untouched
  — it still serves its 4 existing in-process callers (customer
  subledger, AR aging, dashboard recent-activity, CSV export), none of
  which needed to change.
- **Frontend**: the Sales Invoices list gained a real filter bar
  (status + date range) using the existing shared `FilterBar` component
  (same one Products' list screen already uses — no new filter UI
  invented), wired to refetch from the server on every change instead of
  filtering an already-truncated client-side array. New
  `frontend/lib/pagination.ts` mirrors the backend `Page<T>` shape. The
  "New Payment" document picker (which also calls this same endpoint to
  populate its dropdown) was updated to unwrap the new envelope and
  request a generous page size — it's a selection list, not a paged
  screen, so it needed the shape change without needing UI pagination.
- **Deliberate scope boundary**: did not touch `ERPListView`'s shared
  client-side pagination contract — every other list screen in the app
  depends on it, and the component's own existing code comment already
  earmarks a `Page<T>`-based server-side variant as a later, separate
  step "without changing this component's external contract." Extending
  every other module's list endpoint (Purchase Orders beyond the
  `status` filter already added in the Approval Workflow bundle, Vendor
  Bills, Payments, Journal Entries) the same way `list_by_company_page`
  now does is flagged as the natural next slice of this same gap, not
  done here, to keep this bundle's blast radius reviewable.
- **Tests**: `backend/tests/test_sales_invoice_list_pagination.py` (3
  new: three pages across a 5-invoice/page-size-2 spread are distinct
  with zero overlap and zero gaps — the exact scenario the old bug would
  have silently hidden; the status filter narrows correctly; the
  date-range filter narrows correctly). Fixed 2 pre-existing assertions
  in `test_payments_m6_smoke.py` that read the old bare-array response
  shape. 259/259 backend tests, `ruff` clean.
- **Verified live**: opened the real Sales Invoices list — filter bar
  renders (status select + two date inputs), setting the "from" date
  fired a real `GET /sales/invoices?date_from=2026-08-01&page=1&
  page_size=200` request (confirmed via network inspection) and the
  result set + "16 of 16" total-count footer updated correctly, no
  console errors. `tsc`/`eslint` clean.

**Owner Accepted: pending.**

**Purchase Orders + Vendor Bills lists: server-side filtering + real
pagination (2026-08-08)**, committed as `0b7e319`. Sixth bundle picked by
the Product Owner audit methodology — the direct extension of the same
gap Sales Invoices closed, this time to the two Purchasing list screens,
chosen over Document Numbering (bigger/riskier redesign) and
Multi-Currency (an architectural-decision item flagged for an explicit
Owner checkpoint, not started).

- **Real bug found and fixed, not just a missing nice-to-have**: unlike
  Sales Invoices' `limit=500`, `PurchaseOrderRepository.list_by_company`
  and `VendorBillRepository.list_by_company` had **no limit at all** —
  every purchase order and every vendor bill in a company was loaded on
  every render of either list tab, with no page control able to narrow
  it. Same class of bug as the prior bundle, worse in this case since
  there was no cap whatsoever.
- **Backend**: new `PurchaseOrderRepository.list_by_company_page`
  (status/date_from/date_to filters) and
  `VendorBillRepository.list_by_company_page` (partner_id/status/
  date_from/date_to filters) — real SQL `LIMIT`/`OFFSET` plus a matching
  `COUNT(*)`, ordered by the natural date field descending then `id
  desc` as a tiebreaker so paging never skips or duplicates a row.
  `GET /purchasing/orders` and `GET /purchasing/vendor-bills` now return
  the shared `Page[T]` envelope, the same pattern established for Sales
  Invoices. The old unbounded `list_by_company` methods were left
  untouched for their existing in-process callers.
- **Frontend**: both Purchasing list tabs (Orders, Vendor Bills) gained
  the same `FilterBar` component already used by Sales Invoices — status
  select + date range for Orders, plus partner for Vendor Bills is
  reachable through the existing document picker. The "New Payment"
  vendor-bill document picker was updated to unwrap the new `Page<T>`
  envelope and request a generous page size, mirroring the identical fix
  already applied to the invoice picker in the prior bundle.
- **Tests**: `backend/tests/test_purchasing_list_pagination.py` (4 new:
  distinct non-overlapping pages across a 5-order spread; status and
  date-range filters narrow correctly; a 3-bill spread pages correctly
  and the partner filter narrows to exactly the right bill; both list
  endpoints still require authentication). Fixed 5 pre-existing
  assertions across `test_multi_tenancy_isolation.py`,
  `test_purchasing_m4_smoke.py` (3 call sites), and
  `test_payments_m6_smoke.py` that read the old bare-array response
  shape. 263/263 backend tests, `ruff` clean, `tsc`/`eslint` clean.
- **Verified live**: logged into the general demo company (19 purchase
  orders, 18 vendor bills). Purchase Orders list rendered all 19 rows;
  setting the status filter to `draft` fired a real
  `GET /purchasing/orders?status=draft&page=1&page_size=200` request
  (confirmed via network inspection) and correctly narrowed to zero rows
  (every demo PO is `confirmed`). Vendor Bills list rendered all 18 rows
  with the Approve action still working for `matched` bills. In the New
  Payment screen, switching to a vendor payment and selecting "Meshkaty"
  fired `GET /purchasing/vendor-bills?partner_id=...&page=1&
  page_size=200` and the document dropdown correctly showed exactly that
  vendor's 3 bills. No console errors.

**Owner Accepted: pending.**

**Inventory Valuation report (2026-08-07)**, committed as `08369aa`.
Fourth bundle picked by the Product Owner audit methodology — "what is
my stock worth right now?" is a standard report in every reference ERP
(SAP B1, Dynamics 365 BC, Odoo, ERPNext) and was entirely absent here,
even though the costing engine to answer it correctly already existed
in the inventory module (`InventoryValuationService`, built in an
earlier milestone).

- **Backend**: new `InventoryValuationReportService` in the `reporting`
  module (same cross-module-read precedent as `VatReportingService`/
  `SearchService`/`SalesReportingService`) — qty on hand and value per
  product/warehouse. `GET /reporting/inventory-valuation` with the
  standard `format=json|pdf|xlsx` / `lang=ar|en` export and an optional
  `warehouse_id` filter, gated by a new
  `reporting.inventory_valuation.view` permission.
- **Correctness detail that mattered — not just plumbing**:
  `StockQuant.moving_avg_cost` is only ever updated for `average`-method
  companies (`InventoryValuationService.receive_stock` never touches it
  for `fifo`); a FIFO company's real remaining cost basis lives in
  `StockLayer.qty_remaining * unit_cost` instead. The report branches on
  `company.valuation_method` exactly like the transactional engine
  already does — reading the wrong structure for a company's actual
  method would have silently understated or zeroed the report rather
  than erroring, the worst kind of report bug (looks fine, is wrong).
  Caught and handled *before* it could ship, by tracing the existing
  costing engine's own branching logic rather than guessing at a single
  "current cost" column.
- **Frontend**: new "Inventory Valuation" tab on the Inventory page,
  reusing `ReportView` exactly like the existing Product Cardex tab —
  warehouse filter, KPI cards (product count, total value), full table
  with a grand-total footer, PDF/Excel/print export, drill-down links to
  each product's stock card.
- **Tests**: `backend/tests/test_inventory_valuation.py` (6 new:
  average-method valuation reads `moving_avg_cost` correctly; FIFO-method
  valuation sums across `StockLayer` rows rather than reflecting only the
  latest receipt cost; the warehouse filter actually narrows results; PDF
  and Excel export both produce real files; the endpoint requires
  authentication; a company with zero stock returns `[]` rather than
  erroring). 256/256 backend tests, `ruff` clean.
- **Verified live**: opened the real demo company's Inventory Valuation
  tab in the browser — 28 products across "Main Warehouse" and
  "Secondary Warehouse", correct per-row unit costs and totals, correct
  grand total (679,058.21 SAR), no console errors. `tsc`/`eslint` clean.
- **Flagged for later, not blocking this bundle**: list-view server-side
  filtering, document-numbering configuration, multi-currency, recurring
  documents, per-record audit-trail UI, extending Document Delivery /
  Approval Workflow to other document types, and a historical (as-of-
  date, not just "right now") valuation view all remain open and
  un-reassessed, per the Owner's instruction not to re-run analysis.

**Owner Accepted: pending.**

**Dashboard Enrichment (2026-08-07)**, committed as `a2e6752`. Third
bundle picked by the Product Owner audit methodology — the dashboard
was 4 static KPI cards with no drill-down, no trend, no exceptions, and
no activity feed, the single most visible gap against SAP B1/Dynamics
365 BC/Odoo/ERPNext (every one of which opens on more than plain
numbers) and literally the first screen every user sees on login.

- **Backend**: `DashboardService.get_summary` now also returns a real
  6-month sales trend (reuses the existing `sum_total_in_range` per
  calendar month — no new aggregation logic invented), a
  `pending_approvals_count` sourced directly from the Approval Workflow
  built earlier this session (`PurchaseOrderRepository.list_by_company
  (status="pending_approval")` — the dashboard now surfaces exactly the
  gate that bundle built, closing the loop instead of leaving it only
  reachable from the Purchasing screen), and a `recent_activity` feed
  merging the latest sales invoices, purchase orders, and payments
  across three modules, sorted by date. Fully backward compatible — the
  existing `DashboardSummaryOut` fields are untouched, only extended.
- **Frontend**: a hand-rolled SVG bar chart for the trend (six data
  points don't justify a new charting-library dependency), an amber
  actionable alert card that only appears when approvals are actually
  pending (links to Purchasing), a recent-activity feed with per-type
  icons and real drill-down links (reuses the existing
  `source-document-links` map from the Journal Entry traceability work,
  not a new one), and quick-action shortcuts (New Quotation, New
  Purchase Order, Record Payment) — the same "let the user act, not just
  observe" principle the Approval Workflow bundle already established.
- **Tests**: `backend/tests/test_dashboard_enrichment.py` (2 new: a
  company with a real invoice and a real PO stuck above its approval
  threshold shows the correct trend total, the correct pending count,
  and both documents in recent activity, most-recent-first; a company
  with zero activity reports clean zeros rather than erroring). 250/250
  backend tests, `ruff` clean.
- **Verified live**: logged into the real demo company in-browser — KPI
  cards, the amber pending-approvals banner (correctly showing the one
  real PO created earlier this session), the 6-month trend chart
  (Mar–Aug, real totals), quick actions, and a recent-activity feed
  showing real invoices/POs/payments with correct icons, dates, and
  amounts, all with zero console errors. `tsc`/`eslint` clean.
- **Flagged for later, not blocking this bundle**: list-view server-side
  filtering, document-numbering configuration, multi-currency, Inventory
  Valuation report, recurring documents, per-record audit-trail UI, and
  extending Document Delivery / Approval Workflow to Purchase
  Orders/Vendor Bills and Sales Orders/Journal Entries respectively all
  remain open from the two prior audits and are un-reassessed, per the
  Owner's instruction not to re-run analysis.

**Owner Accepted: pending.**

**Document Delivery: Sales Invoice PDF + Send by Email (2026-08-07)**,
committed as `3a6f46e`. Second bundle picked by the Product Owner audit
methodology (review the whole system, pick the highest-value gap, execute
without stopping to propose alternatives). Discovered mid-audit that the
gap was bigger than "add a Send Email button" — this system had zero PDF
for the actual sales invoice document at all; the Standard Reporting
Framework only ever covered tabular reports (Trial Balance, VAT Summary,
...), never a real business-document layout. Per the Owner's rule 5
("fix it if it's in scope"), built the invoice PDF as part of this bundle
rather than deferring it, since email delivery is meaningless without a
real document to attach.

- **Backend — Invoice PDF**: new `shared/documents/invoice_pdf.py` —
  letterhead (company name AR/EN, VAT number, logo if set), bill-to
  block, line items, subtotal/tax/grand-total, and the ZATCA Phase-1 QR
  code regenerated server-side (`qrcode`, new dependency) from the exact
  same TLV `qr_payload` the on-screen invoice page already renders via
  `react-qr-code` — one real payload, two renderings, not two sources of
  truth. Same WeasyPrint HTML/CSS -> PDF technique as the tabular
  reports (correct Arabic bidi via Pango, no hand-rolled canvas). `GET
  /sales/invoices/{id}/pdf`.
- **Backend — Send by Email**: new `shared/email/mailer.py` — stdlib
  `smtplib` behind an `asyncio.to_thread` wrapper (no new async-SMTP
  dependency for what's fundamentally one blocking call per send).
  Platform-level SMTP config (`SMTP_HOST` etc. in `Settings`) — deliberately
  unset in this dev deployment, which makes `EmailNotConfiguredError`
  surface as a real, catchable 422 instead of a silent no-op or an
  unhandled exception (verified live — see below). `POST
  /sales/invoices/{id}:send-email` defaults to the customer's
  `Partner.email` on file; an explicit `to_email` overrides it for a
  one-off recipient without editing the customer record first. New
  `sales.invoice.send_email` permission. `last_emailed_at`/
  `last_emailed_to` on `SalesInvoice` — a real "last emailed" record, the
  same confirmation every reference ERP shows on an invoice, not a fire-
  and-forget action with no trace.
- **Frontend**: Download PDF and Send by Email buttons on the invoice
  detail page; Send by Email opens a dialog (optional recipient override,
  defaults to blank = customer's email on file) and surfaces the exact
  backend error message on failure; a "last emailed" line appears once an
  invoice has been sent.
- **Real bug found and fixed — this one was self-inflicted and serious**:
  while wiring the new PDF/email methods onto `SalesInvoiceService`, an
  edit mistakenly spliced them into the *middle* of the existing
  `_post_journal_entry` method instead of after it, orphaning its last
  line (`invoice.journal_entry_id = posted.id`) as unreachable dead code
  and silently turning off `journal_entry_id` for every new sales
  invoice and credit note going forward. Caught immediately by the full
  regression suite — 5 tests failed (VAT Summary and all 4 AR/AP
  Subledger tests, both of which filter on `journal_entry_id IS NOT
  NULL`) — not discovered live or in production. Fixed by restoring
  `_post_journal_entry` to one contiguous method; full suite re-confirmed
  green afterward. Documented here in full per the Owner's standing
  instruction to report real problems found and fixed, not just the
  feature delivered.
- **Tests**: `backend/tests/test_invoice_email_delivery.py` (6 new: real
  PDF download starts with `%PDF`; send-email defaults to the partner's
  email and records `last_emailed_at`/`last_emailed_to`; an explicit
  recipient overrides the partner's email; no recipient at all is
  rejected with a clear 422 instead of silently doing nothing; a user
  without `sales.invoice.send_email` gets a real 403; and — without any
  mock — the real `send_email` against this environment's actually-unset
  `SMTP_HOST` returns an actionable 422). Real SMTP delivery itself is
  swapped for a fake via `app.dependency_overrides` on a dedicated
  `get_mailer` FastAPI dependency (not a bare function default, precisely
  so it's overridable) — everything up to and including composing the
  email (permission check, PDF generation, recipient resolution, DB
  update) is exercised for real; only the actual SMTP network call is
  faked, the same boundary this codebase's ZATCA sandbox gateway already
  draws for its own external call. 248/248 backend tests, `ruff` clean.
- **Verified live**: downloaded a real invoice PDF from the running
  frontend against the real API (200 OK, correct `Content-Type`); opened
  the Send by Email dialog and submitted it with SMTP unconfigured — the
  dialog rendered the exact backend message ("Outgoing email isn't
  configured for this deployment (SMTP_HOST is unset)"), proving the
  error path is wired correctly end to end, not just asserted in a test.
  `tsc`/`eslint` clean.
- **Flagged for later, not blocking this bundle**: Purchase Order and
  Vendor Bill email delivery are the natural next extension of the exact
  same `shared/email` + attachment-PDF pattern, not built here to keep
  this bundle's blast radius reviewable (a document PDF renderer is
  genuinely a second render function per document type — Purchase
  Order's layout differs enough from an invoice's that it isn't a
  one-line reuse). All 9 other gaps the Approval Workflow bundle's audit
  already flagged (list-view server-side filtering, document-numbering
  configuration, multi-currency, Dashboard richness, Inventory Valuation
  report, recurring documents, per-record audit-trail UI) remain open
  and un-reassessed, per the Owner's instruction not to re-run analysis.

**Owner Accepted: pending.**

**Purchase Order Approval Workflow + Notifications (2026-08-07)**,
committed as `5b88f0f`. Selected by a full-system Product Owner audit
(Owner directive: stop picking standalone report screens, review the
whole system, execute the single highest-value gap) — not the next line
on a backlog. The audit checked 10 cross-cutting areas (notifications,
approvals, list-view UX maturity, document numbering, multi-currency,
email delivery, dashboard richness, inventory valuation reporting,
recurring documents, per-record audit trail) and picked this one because
it was the most concretely confirmed-missing, most universally expected
across SAP B1/Dynamics 365 BC/Odoo/ERPNext, and — decisively — already
explicitly flagged as deferred in this codebase's own
`purchasing/application/services.py` docstring (FR-CORE-052, "PO amount
exceeds threshold," never built). Notifications was picked as the
required companion, not a separate feature: an approval request nobody
gets alerted to is half a feature, and the same audit confirmed
notifications were entirely absent too.

- **Backend — Approval Workflow**: new `company.po_approval_threshold`
  (nullable `Numeric(18,4)`, editable via the existing `PATCH
  /companies/{id}`) — unset means the exact prior auto-confirm behavior,
  unchanged. `PurchaseOrder` gained `created_by_user_id`,
  `approval_status` (`not_required|pending|approved|rejected`),
  `approved_by`, `approved_at`, `rejection_reason`, and a new `status`
  value `pending_approval` (its own `PO_STATUSES` tuple — not the shared
  `DOC_STATUSES` `goods_receipt` also uses). `POST
  /purchasing/orders/{id}:confirm` now routes to `pending_approval`
  instead of auto-confirming when the order total exceeds the threshold;
  new `POST .../{id}:approve` and `POST .../{id}:reject` (with a required
  reason) close the loop, gated by a new `purchasing.order.approve`
  permission. A rejected PO returns to `draft`, editable and
  re-confirmable — not a dead end.
- **Backend — Notifications**: new `notifications` module (own
  `notification` table, `company_isolation` RLS applied in the same
  migration per the Phase 16A/16B lesson). `RoleRepository` gained
  `list_user_ids_with_permission` — the inverse of the existing
  `get_user_permission_codes` — to find every user holding
  `purchasing.order.approve` in a company without hardcoding a fixed
  "approver" concept. The PO's own creator is deliberately excluded from
  their own submission's notification even when they also hold the
  approve permission (proven by a dedicated test). `GET /notifications`,
  `GET /notifications/unread-count`, `POST /notifications/{id}:read`,
  `POST /notifications:read-all` — gated only by authentication (a
  personal inbox, not a company-wide resource; RLS plus a
  `recipient_user_id` filter are the real scope).
- **Frontend**: Company Settings gained the threshold field with an
  explanatory hint; the Purchase Order detail page shows a
  `pending_approval` banner, a rejection-reason banner when applicable,
  and Approve/Reject actions (Reject opens a dialog requiring a reason) —
  all reusing the existing `Can`/permission-gating pattern. New
  `NotificationBell` in the `Topbar` (30s poll — no websocket
  infrastructure exists in this stack yet, matching what every reference
  ERP's web client does before investing in a push channel): unread-count
  badge, dropdown list, click-to-navigate-and-mark-read, mark-all-read.
- **Real bug found and fixed**: `CompanyUpdateRequest`'s audit-log diff
  loop passed each changed field's raw Python value straight into
  `AuditLogRepository.record(old_value=..., new_value=...)`, which is
  typed `str | None` and backs a `Text` column. Every existing field was
  already a string, so this worked by accident; adding the first
  non-string field (`po_approval_threshold: Decimal`) would have handed
  a `Decimal` object to the DB driver for a text column. Fixed by
  stringifying defensively in the loop — a one-line fix, but the kind
  that fails invisibly (only the audit trail for that one field breaks,
  everything else keeps working) until exactly this situation exposes it.
- **Tests**: `backend/tests/test_approval_workflow.py` (5 new: under-
  threshold auto-confirm has no regression; over-threshold requires
  approval and notifies the approver but not the creator; approving
  confirms and notifies the creator; rejecting returns to draft with a
  reason and notifies the creator, and the rejected PO can be re-
  confirmed; a user without `purchasing.order.approve` gets a real 403,
  not just an invisible notification). 242/242 backend tests, `ruff`
  clean.
- **Verified live**: Settings → Company → set a threshold → real `PATCH`
  200. Created and confirmed a real PO over that threshold via the live
  API (not a test client) → `status: pending_approval`,
  `approval_status: pending`, confirmed via direct DB/API inspection.
  Opened that order's real detail page in the browser → the
  `pending_approval` banner, badge, and Approve/Reject buttons all
  rendered correctly with no console errors. `tsc`/`eslint` clean.
- **Flagged for later, not blocking this bundle** (per the audit's other
  9 findings, none of which were dropped silently): list-view filtering
  is entirely client-side (no server-side `status`/date-range query
  params on `sales`/`purchasing` list endpoints — flagged in the same
  audit, `GET /purchasing/orders` now optionally accepts `status` as a
  first step, but the other list endpoints don't yet); no document-
  numbering configuration screen (numbers are still hardcoded
  `f"PO-{n:06d}"`-style formats); no multi-currency transaction support
  beyond a `currency_code` column stub; no "send by email" on any
  document; the Dashboard is still 4 static KPI cards; no Inventory
  Valuation report; no recurring/standing documents; no per-record audit-
  trail UI (global audit log only). Approval Workflow itself is scoped to
  Purchase Orders only — Sales Orders and Journal Entries are natural
  next extensions of the same engine, not built here.

**Owner Accepted: pending.**

**VAT/Tax Summary Report (2026-08-07)**, committed as `ef822dd`: the
standard baseline every Saudi business needs before filing a ZATCA VAT
return — output VAT (sales) vs. input VAT (purchases) for a period,
netted to what's actually owed or refundable. Was an open gap on the
reporting roadmap (flagged, not silently dropped, in the Standard
Reporting Framework entry below).

- **Backend**: new `VatReportingService` in the `reporting` module (same
  cross-module-read precedent as `DashboardService`/`SearchService`).
  Sums sales-invoice and vendor-bill subtotal/tax/total for a date range,
  filtered to documents that actually posted to the books
  (`journal_entry_id is not None` — the same "real accounting impact, not
  a draft" filter AR/AP Aging already applies), and nets credit notes
  against gross sales. `GET /reporting/vat-summary` with the standard
  `format=json|pdf|xlsx` / `lang=ar|en` export support, gated by one new
  `reporting.vat.view` permission.
- **Frontend**: new "VAT Summary" tab on the Accounting page, reusing
  `ReportView`/`ReportPrintHeader` exactly like Trial Balance/Income
  Statement/Balance Sheet — date-range filter, KPI cards (Output VAT,
  Input VAT, and a Net Payable/Refundable card that swaps its own label
  depending on the sign), full breakdown table, PDF/Excel/print export.
- **Real bug found and fixed**: while writing the test for this report,
  discovered the test's own vendor-bill helper never created a default
  warehouse before posting a goods receipt — the goods-receipt endpoint
  correctly 422's without one, which silently left the bill's received
  qty at 0 and the bill stuck in `mismatched` status, so `:approve`
  correctly 409'd. Not a report bug — a test-fixture gap masking the real
  procure-to-pay precondition. Fixed by creating a default warehouse
  before posting, and by asserting intermediate status codes so this
  class of failure surfaces immediately instead of as an opaque 409 three
  calls later. Separately confirmed `SalesInvoice.invoice_date` /
  `VendorBill.bill_date` are always `date.today()` at post time
  (documents are dated when actually issued, not when quoted/ordered) —
  a deliberate design, not a bug, but the test's fixed historical dates
  had to be replaced with dynamic `date.today()`-relative ranges to match
  it.
- **Tests**: `backend/tests/test_vat_summary.py` (4 new: nets output vs.
  input VAT across a real sale + a real procure-to-pay cycle; excludes
  out-of-range documents; PDF/Excel export; permission gate). 237/237
  backend tests, `ruff` clean.
- **Verified live**: full browser walkthrough — logged in as the general
  demo user, opened Accounting → VAT Summary, ran the report against the
  demo company's real data, confirmed the KPI cards and breakdown table
  render correct SAR figures and the Refundable/Payable label switches
  correctly on sign, no console errors.

**Owner Accepted: pending.**

**Global Search — Professional Workspace Layer (2026-08-07)**, committed
as `a8d3ed3`: every reference ERP has one search box that crosses entity
types; a user had to already know which module a customer/invoice/product
lived in to find it before this.

- **Backend**: new `SearchService` in the `reporting` module — the one
  module already permitted to query other modules' tables directly
  (`DashboardService`/`SalesReportingService` already establish this
  rule). Queries partners (by name, AR/EN), products (by name/SKU),
  sales quotations/orders/invoices, purchase orders, and vendor bills (by
  number) — 5 results per type, `ILIKE` substring match. `GET
  /reporting/search?q=...`, gated by one new `search.use` permission —
  RLS still fully scopes every underlying query to `company_id`
  regardless (no cross-company leak even though the permission itself
  isn't split per-entity-type — the same coarse-grain tradeoff
  `audit_log.view` already made).
- **Frontend**: one `GlobalSearch` box added to the `Topbar` (250ms
  debounce, click-outside-to-close, grouped results with a type label per
  row) — wired in exactly once since the Topbar is already global to
  every authenticated page. Extended the existing `source-document-links`
  map (already used for Journal Entry drill-down) with the entity types
  Global Search needed routes for (`partner`, `product`,
  `sales_quotation`, `sales_order`, `purchase_order`).
- **Tests**: 5 new (finds a partner and product by name in one query,
  finds a sales invoice by its real generated number, isolated across
  companies, single-character queries correctly return nothing on both
  ends of the `>=2`-char gate, 401 without auth). 233/233 backend total,
  `ruff`/`tsc`/`eslint` all clean.
- **Verified for real, not simulated**: run directly against the live
  demo company's actual data — `"A4"` found the real "A4 Paper Ream"
  product used throughout this session's own testing; `"trading"` found
  three real customers ("Ahmed Trading Co.", "Al-Faisal Trading Co.",
  "Madinah Textile Trading"); confirmed multiple entity types return
  together in one query (`partner` + `product` for `"de"`).

**Owner Accepted: pending.**

**Attachments — Professional Workspace Layer (2026-08-07)**, committed as
`dc94a9a`: every reference ERP lets a user attach an arbitrary file to any
business document; this system had zero such mechanism outside product/
partner/company logos (which are a different, deliberately-public concern —
see below).

- **Backend**: one polymorphic `attachment` table (`entity_type`/
  `entity_id`, the same `source_table`/`source_id` convention already used
  for stock moves and drill-down), `company_id`-scoped with
  `company_isolation` RLS applied in the same migration (`e4f5a6b7c8d9`).
  Wider content-type allowlist than entity images (PDF, Word, Excel, CSV,
  text, images vs. images-only) via a new `save_attachment_file` in the
  shared media module. Stored under a **separate filesystem root**
  (`attachments_root`, not `media_root`) — `media_root` is deliberately
  served unauthenticated at `/media` (for print headers/logos), and
  business documents must only ever be reachable through the
  authenticated, permission-checked `GET /attachments/{id}/download`.
  New `attachment.view`/`attachment.manage` permissions (one pair for the
  whole cross-cutting concern, matching the `audit_log.view` precedent —
  not one permission per document type).
- **Frontend**: one shared `AttachmentsPanel` (list/upload/download/
  delete, file-type icons, size/uploader/date shown per file) wired onto
  three real document detail pages this pass — Sales Invoice, Purchase
  Order, Vendor Bill — not left as an unused component sitting on zero
  screens.
- **Real bug #1, found and fixed during this bundle**: the Admin-role
  permission-sync query (fixed in the prior Reporting Framework bundle to
  be correct) was still O(roles × permissions) with a correlated
  subquery — fine at realistic production scale, but it saturated this
  session's dev DB (≈9,000 roles accumulated from repeated pytest
  bootstrapping) for 30+ seconds on every API startup, at one point
  visibly degrading the whole dev environment. Rewrote it to pre-filter
  to genuinely *incomplete* roles first via a cheap `GROUP BY`/`HAVING`
  (index-only on the `role_permission` PK) before the expensive
  `CROSS JOIN` — which now only ever touches roles that actually need it
  (≈0 in steady state).
- **Real bug #2, found and fixed during this bundle**: `docker exec
  <api-container> alembic upgrade head` was silently connecting as
  `erp_app` (the least-privileged runtime role — no `CREATE` on schema
  `public`) instead of `erp_migrate`, because `DATABASE_URL_MIGRATE_SYNC`
  isn't set in the `api` container's own environment. DDL migrations must
  go through the dedicated `migrate` compose service (`docker compose run
  --rm migrate`, using `.env.migrate`) — not a code bug, but a real
  operational gotcha now documented here so it isn't rediscovered the
  hard way again.
- **Tests**: 6 new (upload+list, download returns real bytes, delete
  removes it, unsupported content-type rejected with 422, isolated across
  companies, 401 without auth). 228/228 backend total, `ruff`/`tsc`/
  `eslint` all clean.
- **Verified for real, not simulated**: a full upload → list → download →
  delete round trip executed directly against a real invoice belonging to
  the live demo company (not a mock, not just pytest) — confirmed exact
  byte-for-byte content, correct filename via `Content-Disposition`,
  correct content-type, and correct RLS-scoped isolation.
- **Deliberately not built this pass**: attaching files isn't yet wired
  onto every document type in the system (only the three named above) —
  intentional, incremental rollout onto the highest-value document types
  first, not a partial/broken feature; extending to remaining document
  types (journal entries, purchase quotations, sales orders) is now cheap
  since the shared panel and backend already exist.

**Owner Accepted: pending.**

**Users Management — Identity/Access/Governance (2026-08-07)**, committed
as `7c3adb2` — the single most severe gap the full-project re-audit found:
`POST /users` and the role/company-access grant endpoints already existed
with zero frontend, meaning an owner could not add a second real employee
through the product at all.

- **Backend**: `GET /users` (everyone with access to the active company,
  each with their role names — `UserRepository.list_by_company_access`
  joins through `user_company_access`, since "who works here" isn't the
  same as raw tenant membership), `GET /users/{id}` (roles for the active
  company + company-access grants with resolved company/branch names),
  `DELETE /users/{id}/roles/{role_id}` — the symmetric counterpart to the
  already-existing assign endpoint, added because a role checkbox that can
  only ever be checked and never unchecked is a half-built screen (Owner's
  own "no incomplete screens" standard). Reuses `user.view`/`user.create`/
  `user.manage_roles`, already in the permission catalog — no new
  permission or migration needed for the endpoints themselves.
- **Frontend**: Settings → Users (list + quick-create dialog) and a
  per-user detail page (role checkboxes wired to assign/remove, read-only
  company-access list), built as a direct mirror of the existing
  Settings → Security list/detail pattern — same shared components, same
  interaction shape, zero new UI patterns invented.
- **Deliberately not built this pass** (small, real, explicitly deferred
  rather than scope-crept in): granting a user access to a *second*
  company from this screen — no "list all companies in this tenant"
  endpoint exists yet, and building one is its own small backend slice;
  user deactivation/reset-password — no backend support exists for either
  and neither was part of the identified gap (owners can still fully
  onboard and permission a new employee without them).
- **Real bug found and fixed during live verification, not cosmetic**: the
  "keep Admin roles synced with new permissions" mechanism (introduced in
  the Standard Reporting Framework slice, meant to auto-grant permissions
  like `reporting.sales.view` to every existing Admin role) has been a
  silent no-op since the day it was written. It selected from the `role`
  table, which carries FORCE ROW LEVEL SECURITY keyed on company context —
  a context that does not exist at API startup, so the query matched zero
  rows every single time it ran, for every DB user including `erp_app`
  (confirmed directly: `erp_app`/`erp_migrate` both lack BYPASSRLS; only
  the bootstrap superuser has it). Confirmed live via direct SQL that the
  demo company's real Admin role was missing `role.manage` specifically as
  a result. Fixed `seed_core_data()`'s sync to identify Admin roles
  *indirectly* — any role already holding `reporting.dashboard.view` (a
  permission only an Admin role has) — through `role_permission`/
  `permission`, which carry no RLS at all, the same fact migration
  `c1d2e3f4a5b6` already relied on; never touches `role` directly. Added
  migration `d3e4f5a6b7c8` to backfill whatever permission drift had
  already accumulated across every existing company while the sync was
  silently broken (verified: the demo company's Admin role gained
  `role.manage` immediately after applying it).
- **Tests**: 5 new (list shows created users with correct role names and
  empty roles for a freshly-created user; detail shows roles + company
  access; assign→remove is symmetric and immediately reflected; isolated
  across companies; 401 without auth). 222/222 backend total, `ruff`/
  `tsc`/`eslint` all clean.
- **Verified for real, not simulated**: exercised through the live
  authenticated app session (fresh login, not a stored token) against the
  real demo company — created a user, confirmed `GET /roles` which had
  been returning a real 403 before the sync fix now succeeds, assigned
  then removed a role with the change immediately visible in the detail
  response, confirmed company access and role names both correct, and
  confirmed the user count in the list increased correctly.

**Owner Accepted: pending.**

**Standard Reporting Framework (2026-08-07)**, committed as `3138b5c` —
the first of 4 bundles from the full-project re-audit (see the top of this
file). Owner directive: stop building reports one at a time; build one
shared framework all reports inherit, then retrofit it onto every report
that already exists in one pass.

- **Shared renderer** (`backend/src/shared/reporting/`): `export_render.py`
  (`ReportTable`/`ReportColumn` → PDF via WeasyPrint, Excel via openpyxl),
  `export_response.py` (turns a table into a downloadable FastAPI
  `Response`), `labels.py` (shared AR/EN column labels), `company_name.py`
  (AR/EN company-name resolution for report headers), `formatting.py`
  (matches `frontend/lib/format-currency.ts`/`format-date.ts` exactly, so
  exported numbers look identical to the on-screen report).
- **Why WeasyPrint, not reportlab**: a from-scratch canvas PDF library has
  no built-in Arabic bidi/glyph-joining — for a bilingual Arabic-first ERP
  that's the single hardest part of the problem and the likeliest place a
  hand-rolled renderer embarrasses itself. WeasyPrint (HTML/CSS → PDF via
  Pango/Cairo) gets correct Arabic shaping for free; verified directly by
  reading a generated PDF back (`docs` note: rendered "ميزان المراجعة"
  table with properly joined letters and correct RTL column order).
  Adds `libpango-1.0-0`/`libcairo2`/`libgdk-pixbuf-2.0-0`/`fonts-noto-core`
  to the backend `Dockerfile`'s shared base stage (both dev and production
  images).
- **Retrofitted onto all 11 existing reports in one pass** (not one at a
  time): Trial Balance, General Ledger, Income Statement, Balance Sheet
  (accounting); Customer/Vendor Subledger, AR/AP Aging (payments); Sales
  by Customer/Product/Period (reporting); Product Cardex (inventory). Each
  endpoint gained `format=pdf|xlsx` and `lang=ar|en` query params that
  reuse the exact same service/query already computing its JSON response —
  only the serialization branches, no duplicated business logic.
- **Frontend**: `ReportView`'s single `onExport` became `onExportPdf`/
  `onExportExcel`, backed by one shared `reportExportHandlers()`
  (`lib/report-export.ts`) — blob fetch with auth headers, triggers a
  real browser save-as with the server's real filename. Wired identically
  across all 11 report tabs (`accounting/page.tsx`, `sales/reports/page.tsx`,
  `inventory/page.tsx`'s Cardex tab) — copy-once, not eleven separate
  implementations.
- **Real bug found and fixed during live verification**: exported files
  downloaded with the generic filename "report" instead of the server's
  real filename ("trial-balance.pdf" etc.) — `Content-Disposition` isn't
  in the browser's default CORS-safelisted response headers, so
  cross-origin JS (frontend on :3000, backend on :8000) could never read
  it. Fixed with `expose_headers=["Content-Disposition"]` on the CORS
  middleware (`backend/src/api/main.py`) — affects every file-download
  endpoint in the app, not just these 11 reports.
- **Tests**: 8 new (PDF/Excel content-type + magic-byte assertions across
  accounting/payments/reporting/inventory, plus a permission-gating check
  on the export path specifically, since format params could in principle
  bypass a check the JSON path enforces — confirmed they don't). 217/217
  backend total, `ruff`/`tsc`/`eslint` all clean.
- **Verified for real, not simulated**: every export format for every one
  of the 11 reports was exercised through the real running app's live
  authenticated session (fresh login via the actual `/auth/login` endpoint,
  not a stored/mocked token) against real company data — confirmed
  correct `%PDF`/`PK` (xlsx zip) magic bytes, correct byte sizes, and
  (after the CORS fix) correct real filenames including data-derived ones
  like `product-cardex-A4 Paper Ream.pdf`. On-screen click-through in the
  Browser preview pane itself remains blocked this session by the same
  pane-rendering tooling issue noted in the Cardex entry below — not an
  application bug.
- **New gap surfaced, not yet acted on**: none of the report tabs expose
  Group-by/Sort controls in the UI, and there's no "saved filters"
  mechanism yet — both were named in the original Bundle 1 request but
  deferred as separate, smaller follow-ups since the framework's core
  (filters → data → print → export, all standardized) was the priority.

**Owner Accepted: pending.**

**Bundle E — Standard Product Cardex, second slice (2026-08-07)**,
committed as `ba3ef2f`: Owner-requested inventory inquiry — a specific
product, a date range, optional warehouse and document-type filters, "a
standard cardex." Built as a new reusable backend shape
(`opening_qty`/`cardex_lines`/`product_cardex` on `StockMoveRepository`/
`InventoryValuationService`) mirroring General Ledger's opening/running/
closing pattern but for quantities: a single uniform sign rule
(`dest_location_id` set = increase, else decrease) correctly covers
receipts, deliveries, adjustments, and both legs of a transfer without
per-move-type branching. Warehouse filtering matches a move if *either*
its source or destination location belongs to the target warehouse (so a
transfer's two legs are correctly split between the two warehouses' cards).
New route `GET /inventory/stock/cardex` (reuses `inventory.stock.view`,
no new permission). Frontend: 6th "Product Cardex" tab on the Inventory
page (`ReportView`+`ReportPrintHeader`, same shell as every other report
this bundle has built), with the product's image shown next to its name
in the report header — a same-day Owner request, reusing the exact
`EntityImage` component/pattern already live on the Stock Card page, not
a new image mechanism. 3 new backend tests (opening balance and running
qty across an as-of-yesterday/today/tomorrow boundary; a transfer's two
legs correctly scoped by warehouse filter; source-table filter isolates
exactly the matching move type), 211/211 backend total, `ruff`/`tsc`/
`eslint` all clean. **Tested for real, not yet Live Demonstrated**: the
endpoint was exercised through the actual running frontend's authenticated
session (token read from the live app's own `localStorage`, not a
separate script) against real company data — A4 Paper Ream's cardex
returned the exact opening/running/closing sequence its known move history
predicts (receipt +6, delivery −3, transfer −1/+1, cycle-count adjustment
+3 → closing 6), and the `source_table` filter correctly isolated to just
the one matching line. The on-screen click-through (select product in the
UI, click Apply, visually confirm the rendered table) could not be
completed this pass — the Browser preview pane was not compositing frames
(`document.hidden` stayed `true` across a fresh tab and a full navigation,
independent of the app), a client-side tooling gap, not an application
bug. **Owner Accepted: pending** — the on-screen walkthrough is still
owed before this can move past "pending."

**Historical**: 2026-08-04, on top of committed `686c873` (`main`) —
**Unified Address Book / Partner & Contacts**, then committed as
`5aee470` — Implemented and Tested (192/192 backend tests, 9 new; `ruff
check src tests` and `tsc`/`eslint`/frontend production build all clean)
and Live Demonstrated end to end in a real browser session: created one
real Partner ("Ahmed Trading Co.") simultaneously Customer + Vendor +
Employee via the New Partner form; added Billing/Shipping/Other addresses
with correct per-type default enforcement; added a primary contact ("Ahmed
Mohammed", Purchasing Manager) and a second contact ("Sara Al-Otaibi",
Accountant) — each landed as its own real, independently-navigable Partner
row (`is_company=false`, `parent_partner_id` set), not a separate lookalike
table; confirmed via the raw `GET /partners` response that exactly one
"Ahmed Trading Co." row exists (no duplicate) and both contacts have
correct `parent_partner_id`/`job_title`/`is_primary_contact`; confirmed the
same partner appears correctly filtered in Address Book, Customers,
Vendors, and Employees (all four are views over the same table); confirmed
the new Accounting-tab smart links (`/accounting?tab=customer-subledger&partner=<id>`)
land on the right tab, preselect the partner, and auto-run the report with
real (zero, correct) figures; confirmed the duplicate-detection warning
fires non-blockingly on a matching VAT number with a working link to the
existing record, and does not fire on new data; confirmed Arabic/RTL
renders correctly for the new nav entries, all 8 profile tabs, and the
list filters. **Not** re-verified live in this pass: a second-company
switch test for this bundle's new tables specifically (only one company
was attached to the demo login used) — cross-company isolation for
`partner_address` and the new `parent_partner_id` linkage is instead
covered by 4 new automated tests (cross-company 404 on address read/
update/delete, parent-partner-must-be-same-company on create), and by the
pre-existing `company_isolation` RLS policy applied identically to the new
`partner_address` table. Permission gating (create/update/archive all
403 for a zero-role user) is covered by a new automated test, not
re-created manually as a second live browser session, since Bundle 3
already live-verified this exact `Can`/`require_permission` mechanism
end-to-end for other modules. Owner Acceptance for this bundle is
**pending** — never assumed. See the dated entry below for full detail.

**Historical**: 2026-08-04, on top of committed `686c873` (`main`) —
**Bundle 3 — Purchasing/Inventory List & Form Consistency**, then
committed as `89949ec` — 183/183 backend tests (unchanged, no backend code
touched), `ruff`/`tsc`/`eslint`/frontend production build all clean, a
full real business flow live-demonstrated end to end (Purchase Order →
Confirm → Goods Receipt → Vendor Bill → Approve → Stock → Transfer), plus
a second live pass as a permissions-limited user confirming every gated
action correctly disappears (not just disables) and the backend still
returns 403 independently. See the dated entry below for full detail.
The paragraphs further below (2026-08-04 Settings Architecture Foundation
and earlier) are kept verbatim as the historical record and were not
re-verified as part of this pass.

**Historical — last verified 2026-08-02**, against commit `3684edd`
(`main`) plus uncommitted Phase 17D (Payments) work — implemented, then
re-audited
against the full customer/vendor/partial/concurrent business scenarios,
which found and closed two real gaps (no visible payment status, no
concurrency safety on allocation) — Alembic head `5955ce0f8dd6`. Backend
evidence gathered by direct file/DB inspection plus a full-repository
audit agent pass; frontend evidence gathered by a second, independent
audit agent pass — both cited inline below. Phase 17D itself verified
directly (141/141 backend tests, full live browser create-flow, not just
page loads), not by a separate audit agent pass.

**Milestone 0 — Baseline, Governance & Business-Core Readiness** (same
day, under the Owner's "MASTER EXECUTION DIRECTIVE" governance model): a
fresh, same-session re-run of the full verification pass confirmed no
drift since the paragraph above — 141/141 backend tests, `ruff check
src/ tests/` clean (95 pre-existing, unrelated style findings live only in
Alembic-generated `migrations/versions/*.py` boilerplate — not application
code, not a regression, not touched), `tsc --noEmit` clean, `eslint`
clean, `/health` returns `{"status":"ok","database":true}`, Alembic head
still `5955ce0f8dd6`, last commit still `3684edd` — nothing has been
committed yet. This pass produced `docs/erp-ux-standard.md` (new) and a
substantially expanded `docs/master-execution-plan.md` (Business Core
Definition of Done, formal Owner Checkpoint Protocol, per-phase dependency
table, three-tier timeline). No application code was changed to produce
Milestone 0 — see the Milestone 0 checkpoint report for full detail.

**Milestone 0 and Phase 17D are now committed** (`e402571` Payments,
`2135486` Milestone 0 docs). Immediately after, **Milestone 1a —
Accounting Standardization (General Ledger, Income Statement, Balance
Sheet)** was implemented on top of the existing, already-correct Journal
Entry data (no new tables), tested (6 new tests, 147/147 full suite), and
live-verified in a real browser session against real posted transactions —
see `docs/17e-accounting-standardization.md`. **Committed** as `4b9ae08`.
An Owner Acceptance environment (two demo companies, a small idempotent
seed script, click-by-click test instructions) was then prepared and
committed as `43ced32` — see `docs/owner-acceptance-m1a.md`. Milestone 1a
is not yet Owner Accepted (implemented/tested/verified/live-demonstrated
by the Contractor, per §"Status buckets" language below — but the Owner
has not yet personally tried it and approved it).

**Milestone 1b — Customer/Vendor Subledgers, AR/AP Aging, Traceability**
(same day): implemented on top of the same, already-correct Sales/
Purchasing/Payments data (no new tables), including `source_table`/
`source_id` now exposed on Journal Entries and General Ledger lines for
real drill-down. A real correctness bug was found during this Milestone's
own live verification (AR Aging didn't net a credit note against its
original invoice) and fixed, with a regression test proving it — see
`docs/17f-subledgers-and-aging.md` §5. A second, structural finding (no
API exists to grant a new permission to an already-bootstrapped company's
role) is documented in the same file §7, not fixed here — out of scope.
13 new tests, **159/159 full suite**, `ruff`/`tsc`/`eslint`/build all
clean, live-verified in a real browser session (Company C — Milestone
1a's demo company can't reach these two new screens, see §7 above). Owner
Acceptance environment: `docs/owner-acceptance-m1b.md`. **Not yet
committed, not yet Owner Accepted** — see the Milestone 1b checkpoint
report for exact status.

**UI/UX System-Wide Audit (2026-08-03)**: a structured, evidence-based
audit of the entire system from a real Owner/User perspective — live code
reads plus a live walkthrough on real demo data, all 15 areas the Owner
requested (Login/Company Context, Navigation, Master Data, Sales,
Purchasing, Inventory, Payments, Accounting, Reports, Traceability,
Arabic/English/RTL, UI States, Forms, Tables, ERP UX principles). Findings
classified Critical/High/Medium/Low/Already Good with evidence, proposed
solution, Frontend/Backend split, and priority — see
`docs/18-ui-ux-audit.md` in full. Top findings: no company-selection UI
existed at all (silent `authorized_companies[0]` pick); no shared currency
formatter (raw `"1250.0000"` strings on Sales/Purchasing/Inventory vs.
formatted amounts on Dashboard/Accounting/Payments); Purchasing/Inventory
use a weaker hand-rolled list pattern instead of the existing
`ERPListView`; no toast/notification system anywhere; a locale bug found
live (Topbar showed the Arabic company name while Dashboard showed the
English one, same screen). **Audit only — no fixes implemented in this
pass**, per the Owner's explicit instruction to stop and get scope
approval first.

**UI/UX Foundation + Company Context Milestone (2026-08-03, same day,
Owner-approved scope)**: Implemented and Tested. Four shared frontend
utilities (`formatCurrency`, `statusVariant`, `useCompanyName`, a
`Toaster` built on the already-installed `@base-ui/react/toast` — no new
library), applied as minimal swaps (currency formatting, status badges,
success/error toasts) across Dashboard/Sales/Purchasing/Inventory/
Payments/Accounting without touching any table structure. A real Company
Context flow: `/select-company` picker shown whenever a login's
`authorized_companies` has more than one entry, direct entry unchanged
for single-company logins, a "Switch company" entry point in the Topbar.
Backend: `POST /users/{id}/company-access` (grants an existing user
access to another company in their own tenant) and, after a genuine
blocker was found and the Owner explicitly approved closing it,
`POST /companies` (adds a second company to an already-existing tenant —
`/bootstrap` was previously the only creation path and always mints a new
tenant; the creator is auto-provisioned as the new company's Admin, since
there is otherwise no API to give anyone a role in it). One real RLS
company-context bug in the access-grant endpoint was found and fixed
during live two-company verification (not shipped broken). A second real
bug — a hydration race that could bounce an already-logged-in user from
`/select-company` back to `/login` on a hard page load/refresh (zustand's
`persist` middleware rehydrates asynchronously; the dashboard layout
already guards against this exact race, this new page initially didn't)
— was found during the Owner-mandated re-verification pass and fixed.

**Verified**: 165/165 backend tests (13 new, including a full two-company
data-isolation flow), `ruff`/`tsc`/`eslint`/build all clean. **Live
Demonstrated**: full real two-company browser walkthrough — login →
company-selection screen → Company Alpha → data-heavy screen (Customers)
→ switch to Company Beta via the real Topbar control (confirmed opening
and completing the full click-driven journey) and via direct SPA
navigation → Beta's data only, Beta's permissions active, no Alpha data
or stale permissions at any point, no full-page reload used for the
switch itself → switched back to Alpha → Alpha's data correctly restored.
Single-company login (`demo-general@example.com`) confirmed unaffected —
enters directly, no picker. Arabic/English locale correctness confirmed
for company names across Topbar/Dashboard in both companies. Full detail,
file list, and exact repro steps in the two closure checkpoint reports for
this milestone. **Owner Accepted: not yet — pending the Owner personally
trying the real login flow.**

Committed as `1efdd7f` (foundations + Company Context) with a follow-up
commit for the closure fixes (hydration race) — see git log for the exact
hash.

**Governance update (2026-08-02, same day)**: the Owner formalized the
project-management methodology going forward — the Contractor never
self-selects or announces the next Milestone; every checkpoint report
must distinguish Implemented / Tested / Verified / Live demonstrated /
Owner accepted / Deferred / Known Limitation / Out of Scope explicitly;
Owner Acceptance environments (real login, real data, browser-only) are
now mandatory at every checkpoint, not just this one. Four new
cross-cutting product requirements were also recorded for future
Milestones: system-wide document traceability/drill-down, real Customer/
Vendor/Inventory-Item Subledgers (this **reshapes Milestone 1b and
Milestone 5** — see below), a Standard ERP Report Catalog to check future
Milestones against, and a Company-Identity/system-entry requirement (part
UX gap-check, part open architecture question for the Owner/Consultant).
Full detail in `docs/master-execution-plan.md` §D3 and the updated Owner
Checkpoint Protocol in §G. **No application code was changed to produce
this update — planning documents only.**

**UI/UX Evolution: Entity Media Foundation + Master Data Image Support
(2026-08-03, same day, Owner-approved scope, built on top of the now-closed
UI/UX Foundation + Company Context milestone — `1efdd7f`/`1e4c0f9`, not
re-touched except the one shared component extension noted below)**:
Implemented and Tested.

- **Entity Media Foundation** (backend): inspected first — confirmed no
  storage architecture existed anywhere (no upload endpoints, no image
  columns, no upload UI). Built one shared module,
  `backend/src/shared/media/storage.py` (content-type whitelist, 2MB
  limit, uuid4 filenames), used identically for Company/Partner/Product —
  not four separate solutions. Local-disk storage under
  `settings.media_root`, served unauthenticated-but-unguessable via
  FastAPI `StaticFiles` at `/media` — a deliberate tradeoff (print
  headers/statements need plain `<img>` embedding with no way to attach an
  Authorization header), the same pattern the existing ZATCA QR code
  already uses. No new library, no object-storage service — an
  unrequested architecture change was explicitly avoided. New migration
  (`company.logo_path`, `partner.image_path`, `product.image_path`, all
  nullable `Text`), 6 new upload/delete routes, `company.manage`
  permission added for the company-logo actions (`partner.update`/
  `product.update` reused, not duplicated, for partner/product images). A
  new Docker volume (`media_data`) was added to the **production**
  compose file only — dev's existing bind-mount already persists uploads,
  so dev compose was left untouched.
- **Entity Media Foundation** (frontend): one shared `EntityImage`/
  `EntityImageUpload` component pair
  (`frontend/components/erp/entity-image/`) — image, initials fallback,
  placeholder, loading, broken-image fallback, alt text, RTL/LTR, and 5
  responsive sizes, reused identically for Company/Partner/Product per
  the Owner's explicit "one unified pattern, not 4" instruction. The
  shared `apiClient.request()` now also accepts `FormData` bodies (one
  function, not a parallel upload client).
- **Company Logo**: a new Company Profile page (`/company/profile`,
  reachable from the Topbar's company name, which is now a link) —
  upload/change/remove, gated behind the new `company.manage` permission.
  Logo now shows next to the company name in Topbar, Dashboard, the
  `/select-company` picker, and Accounting's Customer/Vendor Subledger
  print-statement headers — company switching still changes name + logo +
  permissions + data together as one unit (verified, not just wired).
- **Customer/Vendor/Product images**: `RecordCard` (the shared detail/edit
  shell) gained one new optional `avatar` slot — used by the Partner and
  Product detail pages to show the entity's image next to its name/code,
  same shell everything else in those screens already uses. Each detail
  page's Overview tab also gained an `EntityImageUpload` block, gated by
  the same `partner.update`/`product.update` permissions the rest of the
  form already requires. List thumbnails added to `PartnerListView`
  (Customers/Vendors) and the Products list, reusing `EntityImage` at
  `size="xs"` inside the existing Name column — no new column, no new
  list pattern.
- **Master Data UX consistency pass**: helpful, specific empty-state
  descriptions added to the Customers/Vendors/Products lists (previously
  a generic "No records found" with no guidance) — the one genuine gap
  found; everything else in Master Data (Products/Customers/Vendors/UOM/
  Categories) was already confirmed on the shared `ERPListView`/
  `FormView`/`RecordCard`/`Can`/`Breadcrumbs`/`EmptyState`/`ErrorState`/
  `Skeleton` pattern per `docs/18-ui-ux-audit.md`'s own findings — not
  rebuilt. Per the Owner's explicit instruction, **Bundle 3** (migrating
  Purchasing/Inventory onto `ERPListView`) was **not** started as part of
  this pass.
- **A real bug found and fixed by this milestone's own new tests**: all 6
  new upload/delete routes originally called `db.refresh()` right after
  `db.commit()` — `db.commit()` ends the transaction that carried the
  RLS `SET LOCAL app.current_company_id`, so the refresh's implicit
  SELECT ran with no tenant/company context and failed RLS
  (`invalid input syntax for type uuid: ""`). Fixed by removing the
  unnecessary refresh (the in-memory ORM object already reflects the
  assigned field). `grep` confirmed this `db.refresh()`-after-`commit()`
  pattern existed **only** in these 6 new lines anywhere in the backend —
  a bug introduced by this milestone's own new code, not a pre-existing
  one, caught before it shipped.

**Verified**: 173/173 backend tests (8 new), `ruff check` clean on all new
code (pre-existing Alembic-boilerplate style findings in
`migrations/versions/*.py` are unrelated and untouched, same as every
prior milestone), `tsc --noEmit`/`eslint`/frontend production build all
clean. **Live Demonstrated**: a fresh company and user were bootstrapped
via the real `/bootstrap` API specifically so the new user's role would
include the newly-added `company.manage` permission (the existing demo
user's role predates it — a known, previously-documented gap: no API
exists yet to add a permission to an already-created role — not a bug in
this milestone). Logged in for real, uploaded a real PNG through the
actual upload API (the same one the UI's file-input form submits to —
browser file-picker automation itself is not supported by the available
tooling, so the upload call was made directly against the real endpoint
and the *result* was verified rendering live in the browser), confirmed
it renders correctly in Topbar, Dashboard, and Company Profile;
confirmed the broken/no-image fallback (initials) after a real Remove
call; confirmed Arabic/RTL rendering (`dir="rtl"`, `lang="ar"`, Arabic
labels and alt text). Created a real Customer and a real Product through
the actual UI forms, uploaded images for both via the real API, confirmed
both render correctly in their list thumbnails, detail-page avatar, and
detail-page image-upload widget. Confirmed the new empty-state copy
renders on an empty Vendors list. **Owner Accepted: not yet — pending the
Owner personally trying it.**

**Committed as `d37661a`.**

**Product/ERP Architecture Reassessment (2026-08-04, planning only, no
code)**: at the Owner's explicit direction, stopped feature work to
reassess against the original plan and against Odoo/ERPNext/Microsoft
Dynamics 365 Business Central/SAP Business One official documentation.
Found the current Partner model (customer/vendor unified via flags)
already matches a real, internationally-used pattern (SAP Business
One's Business Partner) rather than being a gap — recommended **not**
pursuing a full Party/Contact/Employee unification now (no mainstream
system merges Employee into it either, including Odoo's own
`res.partner`). Identified the two most foundational, genuinely missing
pieces as (1) no Settings/configuration architecture at all — even the
company's own legal name was not editable after `/bootstrap` — and (2)
no way to change an already-created role's permissions, a real
operational blocker hit twice in the prior two milestones. Recommended
**Settings Architecture Foundation** as the single next milestone over
several competing candidates (Address Book, Audit Trail UI, Party 360°
view) — full detail in the milestone entry immediately below. No
application code was changed to produce this reassessment.

**Settings Architecture Foundation — Company Settings + Security
(2026-08-04, same day, Owner-approved scope)**: Implemented and Tested.

- **Settings Shell**: one reusable layout (`SettingsShell`, a section
  nav + content area) every future settings area — Sales/Purchasing/
  Inventory/Accounting/Payments module settings, System settings — will
  extend without redesigning navigation or layout, per the Owner's
  explicit "design the architecture right the first time" instruction.
  Only two sections are actually built now (Company, Security); no
  placeholder nav entries for unbuilt sections, per this project's
  standing "no fake nav entries" rule.
- **Company Settings** (`/settings/company`, supersedes the prior
  milestone's `/company/profile`, now removed — one screen, not two
  competing ones): the first endpoint able to edit a company's own
  `legal_name`/`legal_name_ar`/`vat_number`/`cr_number` at all — until
  now these were fixed at `/bootstrap` time with zero way to correct
  them (confirmed live: the prior milestone's Company Profile page
  showed these fields read-only specifically because this endpoint
  didn't exist). Deliberately excludes `base_currency`/
  `valuation_method`/`zatca_environment` from editing — each drives
  historical monetary/costing/e-invoicing correctness and needs its own
  guarded flow, not a plain field edit; documented in the schema, not a
  silent gap.
- **Security — Roles & Permissions** (`/settings/security`): the fix
  for a real, previously-documented gap — a role's permissions used to
  be fixed at creation time (`/bootstrap` or `POST /companies`) with no
  API to change them afterwards, hit twice in the prior milestone
  (needed a fresh company each time just to test a newly-added
  permission). Now: list roles, create a custom role, and edit any
  role's full permission set via a checkbox matrix grouped by module —
  changes take effect immediately for any user holding that role, no
  logout required (the frontend invalidates its own permission cache on
  save).
- **A real cross-company data bug found and fixed by this milestone's
  own test**: the Company VAT-uniqueness pre-check queried
  `Company` by VAT number under the caller's own RLS company context,
  which made another company's row invisible to the query — so the
  pre-check silently passed even though the database's own unique index
  would then reject the update. Fixed by catching the `IntegrityError`
  from the actual write instead of trusting a pre-check that RLS can
  make unreliable across companies for a globally-unique column — caught
  by this milestone's own new test before shipping, not by the Owner.

**Verified**: 183/183 backend tests (10 new), `ruff`/`tsc`/`eslint`/
frontend production build all clean. **Live Demonstrated**: on a
freshly-bootstrapped company (needed so the account's Admin role
included the new `role.manage` permission — same known, unresolved
"can't add a permission to an old role via itself" limitation this very
milestone fixes for every *future* permission, just not retroactively
for roles that predate it) — edited Company Settings and watched the
change propagate instantly to Topbar/Dashboard; opened the Admin role,
unchecked its own `company.manage` permission, saved, and watched
`/settings/company` immediately fall back to read-only with **no
logout, no reload**; re-granted it and watched the edit form return;
created a new custom role from empty, confirmed it started with zero
permissions. Confirmed Arabic/RTL rendering (`dir="rtl"`, translated
nav/labels — permission codes themselves render in formatted English,
a deliberate scope boundary, not a bug) and mobile-responsive behavior
(the section nav collapses to a horizontal scroll row below the `sm`
breakpoint). **Owner Accepted: not yet — pending the Owner personally
trying it.**

**Committed as `686c873`.**

**Bundle 3 — Purchasing/Inventory List & Form Consistency (2026-08-04,
same day, Owner-approved scope)**: Implemented and Tested. Closes the
original UI/UX audit's (`docs/18-ui-ux-audit.md`, finding A1) core
"two different UI qualities in the same app" problem — Purchasing's two
tabs (Orders, Vendor Bills) and all four Inventory tabs (Warehouses,
Stock, Moves, Transfer) previously used a hand-rolled `<Table>` inside
`<Tabs>` with no search, sort, or pagination, ad hoc empty-row markup
instead of the shared `EmptyState`/`ErrorState`, and no permission gating
on the Create/Approve buttons at all — every mutating action was visible
and clickable regardless of the logged-in user's actual permissions.

- **Purchasing**: both tabs rebuilt on `ERPListView` — real search/sort/
  pagination, `<Can>`-gated "New purchase order" and "Approve" actions,
  shared empty states with real guidance copy. A genuine "buried
  information" gap found and fixed along the way: the Orders and Vendor
  Bills lists never showed *which vendor* a document was for at all —
  added a `usePartnerLabel()`-style resolver (mirrors Inventory's existing
  `useProductLabel()` pattern) so the Vendor column now shows the real
  name, not just a number.
- **Inventory**: all four tabs rebuilt the same way. The three inline
  quick-create forms (Warehouse, Receive Stock, Transfer) deliberately
  stay inline rather than becoming full `FormView` pages — moving them
  would add clicks for no UX benefit, the opposite of this project's
  "minimum clicks" standard — but each is now wrapped in `<Can>`, closing
  the same permission-visibility gap Purchasing had.
- **A dead shared component activated, not reinvented**: `PermissionDenied`
  (`components/erp/states/permission-denied.tsx`) existed in the codebase
  since Phase 17A but had **zero real call sites** anywhere in the app
  until this milestone — now used for Inventory's Transfer tab when the
  caller lacks `inventory.transfer.create`, instead of inventing new
  fallback markup.

**Verified**: 183/183 backend tests (unchanged — this milestone is
frontend-only, confirmed no backend file was touched), `ruff`/`tsc`/
`eslint`/frontend production build all clean. **Live Demonstrated**: a
complete real business flow end to end on a freshly-bootstrapped company —
created a real Vendor and Product, created Purchase Order PO-000001
(3,000.00 SAR), confirmed it, received the goods, registered and approved
Vendor Bill BILL-000001 (3,450.00 SAR with VAT), confirmed Stock Levels
showed 10 units at the correct average cost, created a second warehouse,
transferred 4 units between warehouses, and confirmed the transfer
appears correctly in Stock Moves — every number correct at every step, no
business-logic drift from the UI changes. Separately logged in as a
freshly-created, deliberately permission-limited user (view-only role)
and confirmed live that every gated action (New Order, Approve, New
Warehouse, Receive Stock, Transfer) is genuinely **absent**, not just
disabled, and that a direct API call from that same user still gets a
real `403` from the backend independently of the UI (defense-in-depth,
not just a client-side hide). Confirmed Arabic/RTL rendering (`dir="rtl"`,
full label translation) on both Purchasing and Inventory. **Owner
Accepted: not yet — pending the Owner personally trying it.**

**Not yet committed** — see the milestone's checkpoint report for exact
file list and status.

---

## 1. Where we are right now

- **Git**: 8 commits on `main`. `a08586d` (initial nucleus: Phases 1–15 of
  the original methodology, Backend M0–M5, Frontend, Docker/deployment,
  root docs), `731219c` (RLS tenant-isolation hardening), `115f966` (CORS
  env-driven fix), `4ccc758` (Phase 16B idempotency/concurrency docs),
  `ccac510` (duplicate-invoice fix), `3a344d1` (**Phase 17B** — master
  data), `474760c` (**Phase 17A** — UX/reporting foundation), `3684edd`
  (**Phase 17C-RLS** — database runtime role hardening, just closed).
- **Database**: 46 application tables, all under real, enforced RLS
  (`erp_app` — `NOSUPERUSER`, `NOBYPASSRLS`; verified in Phase 17C-RLS,
  not assumed). 16 migrations, head `0fc571b91522`.
- **Backend**: 7 modules (identity, accounting, sales, zatca, inventory,
  purchasing, reporting), ~46 API endpoints, Route → Service → Repository
  → Domain layering, consistent `require_permission()` guarding on every
  mutating endpoint except the one deliberate exception (`POST /bootstrap`).
- **Frontend**: Next.js App Router, 24 routes, a real shared component
  library (`components/erp/*`) from Phase 17A — but adopted by only 2 of 6
  module areas so far (see §2).
- **Tests**: 130 passing (13 files) — smoke/milestone tests per module,
  multi-tenancy isolation, invoice-duplication, direct RLS enforcement,
  login/2FA integration, ZATCA worker regression. All integration-level
  (real HTTP + real dockerized Postgres); no isolated fast unit-test layer
  exists for pure domain logic; no frontend tests at all.
- **A naming note that matters going forward**: the original Phase 17
  blueprint (`docs/17-erp-standardization-master-blueprint.md`) sequenced
  **Phase 17C as "Payments"** (pulled forward because it blocks 5 other P0
  items). A different, unplanned, higher-priority phase — the
  superuser-runtime-role security finding from Phase 17B testing — took
  the "17C" slot instead and shipped as **Phase 17C-RLS** (commit
  `3684edd`). The originally-planned Payments phase is tracked here as
  **Phase 17D — Payments** to remove the ambiguity, and — as of this
  update — **it's implemented and verified, not committed yet**: new
  `payment`/`payment_allocation` tables (migration `5955ce0f8dd6`, RLS
  from creation), a new `backend/src/modules/payments/` module, a
  `/payments` + `/payments/new` frontend, and 6 new tests, all passing
  alongside the full 136-test suite. Full detail in
  `docs/17d-payments.md`; §6 below is kept as the original plan for
  historical record, with a status note added.

---

## 2. Completion Matrix

Legend: 🟢 Production-ready · 🟡 Partial/working-but-incomplete · 🔴 Not started · ⚪ Deferred/out of scope by design

| Area | Planned (source) | Current State | Completion | Evidence | Remaining |
|---|---|---|---|---|---|
| **Core Architecture** | Phase 8 | Modular monolith, one-way module dependencies (Identity has zero downstream deps; Accounting is consumed, never calls out except one event listener; Sales/Purchasing/Inventory call Accounting directly) | 🟢 90% | domain/application/infrastructure/api present in all 7 modules; event-driven `CompanyRegistered` seeding (`accounting/__init__.py`) | no unit-test layer isolating domain logic from I/O |
| **Database Design** | Phase 7 | 46 tables, UUID PKs, `tenant_id`+`company_id` envelope, soft-delete on identity-root tables, audit tables | 🟢 90% | direct `pg_tables` query this session | `role_permission`/`user_role` carry no RLS policy of their own (low-severity, §4) |
| **Multi-tenancy / RLS** | Phase 7 §1.4, 16A, 17C-RLS | Both policy families enforced by the real runtime role (`erp_app`), `FORCE ROW LEVEL SECURITY` everywhere, default-deny proven | 🟢 100% | 24/24 direct RLS tests | none open |
| **Security / Roles** | Phase 17C-RLS | `erp_migrate`/`erp_app` split, least-privilege grants, login/2FA escape hatch, 3 separate context-ordering bugs found and fixed (ZATCA worker, cycle-count, bootstrap) | 🟢 100% | `docs/17c-rls-runtime-role-hardening.md` | historical pre-16A dump-restore limitation (accepted); `role_permission`/`user_role` RLS gap (§4) |
| **Identity/Auth/RBAC** | Phase 2, 7 | Bootstrap, JWT+refresh, TOTP 2FA, 47-permission RBAC, VAT/email/SKU uniqueness, category-cycle detection | 🟡 75% | `identity/api/routes.py`; `AuditLogRepository.record()` only called for `assign_role` in this whole module | no user deactivate/lock, no password-reset flow, no TOTP-enrollment endpoint (verify-2fa exists, nothing sets `totp_secret` except this session's manual SQL test setup), no `Company` update endpoint, no Partner deactivate, no role-management UI |
| **Accounting** | Phase 2, blueprint §8 | CoA, journals, JE draft/post/reverse with real immutability + balance guards, fiscal-period open/close, Trial Balance, General Ledger, Income Statement, Balance Sheet (Phase 17E / M1a — committed `4b9ae08`), **Customer/Vendor Subledgers, AR/AP Aging, JE source-document drill-down (Phase 17F / Milestone 1b — new, not yet committed)** | 🟢 85% (Implemented/Tested/Verified/Live-demonstrated; **not yet Owner Accepted** — environment ready, see `docs/owner-acceptance-m1a.md` and `docs/owner-acceptance-m1b.md`) | `payments/api/routes.py` (4 new endpoints — hosted in Payments module by design, see `docs/17f-subledgers-and-aging.md` §2); 13 new tests incl. a direct Subledger-vs-General-Ledger reconciliation assertion; live-verified in browser (Company C) incl. a real bug found and fixed during this Milestone's own verification (§5 of the 17f doc) | no period-closing/closing-entry mechanism (documented, not a bug); Vendor Bill has no detail page yet so Vendor Subledger rows aren't clickable (Sales/Purchasing Standardization territory); `CostCenter` is schema-only; no multi-currency JEs, no bank reconciliation; RBAC permission-catalog growth doesn't propagate to already-bootstrapped companies — a real, structural finding, §7 of the 17f doc, not fixed in this Milestone |
| **Sales** | Phase 2, blueprint §9 | Quotation→confirm→Order→Invoice(clearance/reporting)→Credit-Note, real B2B/B2C routing, real double-invoice race prevention (app check + DB partial unique index) | 🟡 50% | `sales/api/routes.py`; **zero `AuditLogRepository` calls in this module** | no payment (0% — no table), no customer statement, hardcoded flat 15% VAT per line ("follow-up" per code comment), no price lists/discounts, no `:cancel` despite `cancelled` being a valid status, `SalesOrderLine.qty_invoiced` field exists but is dead code (never incremented), Delivery is not a distinct document (deliberate) |
| **Purchasing** | Phase 2, blueprint §10 | PO→confirm→Goods-Receipt→Vendor-Bill, real 3-way match (qty/price, human-readable mismatch reasons persisted) blocking approval | 🟡 50% | `purchasing/api/routes.py`; **zero `AuditLogRepository` calls**; module's own service docstring admits *"Approval routing... deferred — the nucleus auto-confirms every PO"* | no vendor payment (0%), no vendor statement, no PO approval-threshold workflow (self-admitted gap), no RFQ (deliberate), no `:cancel`, no bill without a PO (unplanned expenses unsupported) |
| **Inventory** | Phase 2, blueprint §7 | Warehouses/locations, FIFO/average valuation (verified oldest-first / recompute formula), transfers, cycle-count with real adjustment + journal posting | 🟡 55% | `inventory/api/routes.py`; **zero `AuditLogRepository` calls** despite moving financial value | no stock card, no reorder rules (no min/max fields exist), `/stock/receive` is an ungated manual-adjustment backdoor (no reason code), no valuation report, no serial/lot tracking, **cycle-count has a backend workflow with zero frontend UI at all** |
| **ZATCA e-invoicing** | Phase 2 | Real hash-chaining, real TLV QR (tags 1–6 populated), B2B-clearance/B2C-reporting routing, correct async worker RLS-context ordering | 🟡 40% (pipeline works end-to-end; **0% production-ready by the code's own admission**) | `sandbox_gateway.py`: *"NOT A REAL ZATCA INTEGRATION"*; `signing.py`: HMAC placeholder explicitly documented as *not* a real Cryptographic Stamp; no CSID onboarding flow | needs genuine ECDSA/secp256k1 signing + CSID certificate + real ZATCA endpoint integration — a compliance project of its own, correctly out of nucleus scope so far |
| **Reporting** | Phase 2, blueprint §11 | Dashboard (4 KPIs), CSV export ×2 (sales invoices, audit log) | 🔴 15% | `reporting/` — 85+55+20+17+13 lines total across all files, exhaustively read | no shared report/filter architecture, no GL/P&L/Balance Sheet/aging, no PDF export (explicitly deferred in code comment), only 2 of 7 modules have any export at all, one blanket permission for all exports |
| **Master Data / Address Book** | Phase 17B, Unified Address Book bundle (2026-08-04, uncommitted) | Product, ProductCategory, UnitOfMeasure unchanged; Partner is now the single master entity for Company/Individual, Customer/Vendor/Employee, and Contact Person (via `parent_partner_id`, no separate contact table) — Address Book/Customers/Vendors/Employees are filtered views over one table; multi-address (`partner_address`, billing/shipping/other, per-type default); non-blocking duplicate-detection warning on create; archive/restore; smart Accounting-tab links (deep-linked, auto-run subledger) | 🟢 85% (Implemented/Tested/Live Demonstrated; **not yet Owner Accepted**) | `docs/project-progress.md` dated entry above; 9 new backend tests (192/192 total); migration `b2c4e6f8a1d3`; live-demonstrated full flow (Customer+Vendor+Employee partner, 3 addresses, 2 real contacts, cross-view/RTL/deep-link checks) | Sales/Purchasing document flows do not yet reference `partner_address` rows (deliberately deferred, table designed to be FK-able when they do); `partner.address` JSONB kept post-backfill, not yet dropped (deliberate, per Owner instruction); Module Settings for Address Book deferred; no relation tabs beyond Accounting smart links; no bulk import/export |
| **Frontend — Design System** | Phase 17A | Real shared library: `ERPListView` (search/sort/paginate/column-picker), `FilterBar`, `FormView`, `RecordCard`, `Can`, empty/error/not-found states — genuinely functioning, not shells | 🟡 70% | `components/erp/*`; but **only Master Data + Sales Quotations actually use it** — Accounting/Inventory/Purchasing are bespoke `<Table>` reimplementations | `zod`+`react-hook-form` are installed but have **zero usage anywhere** — every form is hand-rolled `useState`, no schema validation; `coming-soon.tsx`/`permission-denied.tsx` are dead code |
| **Frontend — Module UIs** | Phase 12, 17A/B | 24 routes; real i18n/RTL (228 parallel EN/AR keys, real `dir` flip on `<html>`, logical CSS properties, verified live this session) | 🟡 55% | frontend audit agent, per-module detail below | **no Sales Order or Sales Invoice list page exists at all** (only reachable via deep link from a quotation/order); Accounting/Inventory/Purchasing tabs have no search/filter/sort/pagination and **no `isError` handling** (fail silently blank); workflow-action buttons (confirm/post/reverse/approve) are gated by document status but **not by permission** anywhere outside Master Data's create buttons; no UI at all for user/role/branch/audit-log management despite backend support; vendor bills have no detail page |
| **Testing** | Phase 11 | 130 integration tests, all against real Postgres/RLS, no mocks on security paths | 🟡 65% | this session's full-suite runs | 100% integration-level, no domain unit tests, no frontend tests |
| **DevOps** | Phase 14 | Dev+prod Compose, 3-tier DB roles, idempotent bootstrap, health checks, documented runbook | 🟢 95% | `infra/`, `docs/14-deployment.md`, this session's cold-restart verification | no CI pipeline file in repo — tests/lint documented but not automated on push |
| **Documentation** | Phase 15 | 19 docs files (now incl. this one), phases 1–11/14/16/16b/17/17a/17b/17c all current | 🟢 85% | `docs/` listing | no dedicated 12/13/15 files (READMEs used instead, prior explicit decision) |
| **Payments** | Blueprint §21 (originally "17C") | Customer/vendor payment recording with multi-document allocation, real cash/bank↔AR/AP journal posting, RLS from creation, live paid/partial/unpaid status per document, concurrency-safe allocation (row-locked), real invoice/bill picker in the UI | 🟢 85% | `backend/src/modules/payments/`; migration `5955ce0f8dd6`; `docs/17d-payments.md`; 11/11 new tests incl. a real concurrent-double-payment race test; live-verified full create flow in the browser | no refund/credit-application flow (evaluated, genuinely deferred — needs its own design decision, not a minimal fix), create form still hand-rolled `useState` (evaluated twice, still judged not worth a first-ever pattern introduction — see 17d doc §12), picker doesn't hide already-fully-paid documents (cosmetic), not yet committed |

---

## 3. Cross-cutting findings (apply across multiple modules — not fixed now, tracked here)

These surfaced independently from both audit passes and are systemic
rather than one module's bug. Per the "stop and report, don't silently
expand scope" discipline this project has used since Phase 17C-RLS, none
of these are fixed as a side effect of the next phase unless directly
blocking it — they're recorded here so they aren't rediscovered from
scratch later.

1. **Audit trail is real but sparse.** `AuditLogRepository.record()` is
   called in exactly 3 places system-wide: Identity's `assign_role`,
   Accounting's `:post` and `:reverse`. Sales, Inventory, and Purchasing —
   arguably the modules with the *most* financially material actions
   (invoice issuance, stock movement, PO/bill approval) — call it zero
   times.
2. **No `:cancel` endpoint exists anywhere**, despite `cancelled` being a
   valid, modeled status on `Quotation`, `SalesOrder`, `SalesInvoice`, and
   `PurchaseOrder`.
3. **No genuine maker-checker approval exists.** Every "approval"
   (vendor-bill approve, cycle-count approve) is gated by an automated
   rule (3-way match, discrepancy calc) or a permission check — nothing
   requires the approver to differ from the creator. Purchasing's own
   service docstring self-admits PO approval-threshold routing is
   deferred.
4. **Frontend forms don't use the validation libraries already
   installed.** `zod` and `react-hook-form` are both in `package.json`
   with zero real usage — every create/edit form is hand-rolled `useState`
   with manual required-field checks, no field-level error messages.
5. **Workflow-action buttons aren't permission-gated in the UI**, only by
   document status. A user who can see a quotation/order/invoice/PO/bill
   detail page can click Confirm/Invoice/Post/Reverse/Approve regardless
   of their actual RBAC permissions — the backend still enforces the real
   check (`require_permission`), so this is a UX/consistency gap, not a
   security hole, but it means the UI currently lies about what a user can
   do.
6. **Error states are inconsistent.** Master Data and Sales Quotations
   (the `ERPListView`-based pages) handle loading/error/empty correctly.
   Accounting, Inventory, and Purchasing's bespoke tab tables have no
   `isError` handling at all — a failed fetch renders as a silently empty
   table, indistinguishable from "no data."
7. **`role_permission` and `user_role` carry no RLS policy of their own**
   (noted in §2's Security row) — low severity since both parent tables
   (`role`, `app_user`) are RLS-protected, but a direct unfiltered query
   against either join table would return cross-tenant role/permission ID
   pairs.

---

## 4. Status buckets

**COMPLETED**: Multi-tenancy/RLS enforcement, Security/runtime roles,
Master Data.

**PARTIALLY COMPLETED**: Identity/RBAC, Accounting, Sales, Purchasing,
Inventory, ZATCA (pipeline works, not production-certified), Reporting,
Payments (implemented, verified, not committed — see §6), Frontend design
system (built but under-adopted), Frontend module UIs, Testing,
Documentation.

**NEXT**: Milestone 0 (`e402571`, `2135486`), Phase 17D (Payments,
`e402571`), and Milestone 1a (`4b9ae08`, `43ced32`) are all **committed**.
Milestone 1b — Customer/Vendor Subledgers, AR/AP Aging, and JE
source-document traceability — is **implemented, tested (159/159 full
suite), verified, and live-demonstrated**, with its own Owner Acceptance
environment ready (`docs/owner-acceptance-m1b.md`), but **not yet
committed**. Both Milestone 1a and 1b await the Owner's own hands-on test
before either can be called Owner Accepted. Per the governance update
recorded above, the Contractor does not self-select or begin the next
Milestone after 1b — the next roadmap item (Reporting Polish, Milestone
2) is recorded in `docs/master-execution-plan.md` as the technically-
unblocked candidate only, not a started or announced next step.

**DEFERRED**: Customer/Vendor/Product cards + statements, Stock card +
reorder rules, remaining analysis reports, RBAC role management UI, real
ZATCA production certification, Payments' own known limitations (§12 of
`docs/17d-payments.md`: refund flow, `zod`+`react-hook-form` adoption,
picker doesn't hide already-fully-paid documents), the UX gaps catalogued
in `docs/erp-ux-standard.md` §2 (shared formatting utility, notification/
toast system, permission-gate audit outside Master Data/Payments), and the
rebuildable Demo Data mechanism (`docs/master-execution-plan.md` §F,
scheduled as Milestone 3).

**OUT OF SCOPE** (explicit prior decisions): HR, CRM, POS, Manufacturing,
Projects, Construction, AI, E-commerce, BI, DMS; multi-currency depth;
serial/lot tracking; Delivery as a distinct document; RFQ.

**KNOWN LIMITATIONS**: historical pre-16A dump-restore needs a one-time
superuser credential (documented, accepted); `role_permission`/`user_role`
RLS gap (§3.7); sparse audit trail (§3.1); no `:cancel` anywhere (§3.2);
no CI pipeline; no domain-unit or frontend test layer; frontend form
validation libraries installed but unused (§3.4); UI workflow buttons not
permission-gated (§3.5); ZATCA is sandbox-only, not production-certified.

---

## 5. DevOps discipline carried forward

Per Phase 17C-RLS's own lesson: any new feature must be verified against
the real `erp_app` runtime role (never the bootstrap `erp` superuser), and
any migration privileged operation must run through `erp_migrate` via the
`migrate` compose service. New RLS-protected tables get their policy in
the same migration that creates them, not bolted on after.

---

## 6. Phase 17D — Payments (kept as the original plan; now implemented and re-audited)

> **Status update**: everything below was written as the forward-looking
> plan before implementation started. It's kept as-is for the historical
> record of *why* Payments was chosen and *how* it was scoped. The actual
> result — what shipped, a re-audit pass that found and closed two real
> business-completeness gaps (payment status wasn't visible anywhere;
> concurrent payments could jointly over-allocate an invoice), exact test
> counts (11/11 new, 141/141 full suite), and remaining known limitations
> — is in `docs/17d-payments.md`, now the authoritative reference for this
> phase. The matrix in §2 reflects the real, verified state (🟢 85%), not
> this section's original estimate.

### Why this and not something else

The original blueprint's own dependency analysis (§18, §21 of
`17-erp-standardization-master-blueprint.md`) already established this,
and nothing since has changed it: **Payments is the one item that, if
delayed, silently blocks five other P0/P1 items** — AR/AP aging, customer
statements, vendor statements, the "balance" portion of both Customer and
Vendor cards, and (indirectly) General Ledger/P&L completeness. Verified
fresh this session by both audit passes: zero `payment`/`VendorPayment`
table, zero `due_date` field anywhere in `sales`/`purchasing` models —
this is a real schema gap, not just a missing report. Following the
"vertical slice" standard, Payments is also the smallest genuinely new
module left — smaller than Accounting Standardization or Sales/Purchasing
Standardization.

### Objective

A minimal, correct Payments module: record a customer payment against one
or more sales invoices, record a vendor payment against one or more
vendor bills, post the matching cash/bank journal entry, update the
invoice/bill's outstanding balance. This unblocks aging and statements
without building them yet.

### Business value

Closes the single most-cited gap in the blueprint's "Standard ERP v1"
definition. Without it, this system cannot answer "how much does this
customer owe me" — a baseline expectation for any ERP.

### Dependencies

- **Architectural**: none blocking — reuses the existing one-way module
  dependency pattern (Payments depends on Identity + Accounting, same
  shape as Sales/Purchasing today).
- **Database**: new `due_date` column on `sales_invoice`/`vendor_bill`
  (additive, nullable); new `payment` + `payment_allocation` tables, both
  `company_id`-scoped with `company_isolation` RLS **from the same
  migration that creates them** — not bolted on after, the exact mistake
  Phase 16A/16B had to retrofit.
- **Security/RLS**: verified against the real `erp_app` role, same
  discipline as `tests/test_rls_enforcement.py`, not assumed.
- **Accounting**: posts a real journal entry (cash/bank debit, AR/AP
  credit) — reuses `JournalEntryService`, applies the same
  idempotency/locking discipline Phase 16B established for invoice
  posting (double-payment race prevention, matching Sales' existing
  partial-unique-index pattern).
- **Existing implementation to reuse, not duplicate**: `JournalEntryService`,
  `require_permission()` pattern, `ERPListView`/`FormView`/`RecordCard`
  (and — unlike prior phases — this is the first module to actually wire
  up `zod`+`react-hook-form` for its create form, closing part of §3.4
  as a side effect of new work, not a retrofit of old work), `AuditLogRepository.record()`
  called on payment creation (closing part of §3.1 for this module only —
  not retrofitting Sales/Purchasing/Inventory's existing gap).

### Design decisions being made now (standard ERP patterns, not
architectural ambiguity — proceeding without a stop):

- One payment can allocate across multiple invoices/bills (many-to-many
  via `payment_allocation`) — not a rigid one-payment-one-invoice model.
- Overpayment is recorded as an unallocated credit balance on the payment
  record, not auto-refunded — refund handling is a deferred item, not
  silently dropped.
- Payment methods: cash/bank only for v1 (`cash_or_bank_account_id`
  pointing at an `account` row) — no payment-gateway integration.
- The new payment-recording form will use `zod`+`react-hook-form` (already
  installed, unused everywhere else) rather than the hand-rolled
  `useState` pattern every other form in the app currently uses — a
  deliberate, scoped exception, not a silent app-wide refactor.

### Expected footprint

- **Database**: 1 migration (new columns + 2 tables + RLS policies).
- **Backend**: new `backend/src/modules/payments/` module
  (domain/application/infrastructure/api); small additions to
  `sales`/`purchasing` schemas to expose `due_date` and outstanding-balance
  fields.
- **API**: `POST /payments`, `GET /payments`, `GET /payments/{id}`
  (customer/vendor distinguished by a `payment_type` field or two thin
  routes — finalized during implementation).
- **Frontend**: a Payments list/create page (on `ERPListView`+`FormView`,
  new nav entry), payment-recording action surfaced from invoice/bill
  detail views.
- **Tests**: new module test file (payment recording, allocation, balance
  update, RLS isolation against real `erp_app`) + full regression of the
  existing 130-test suite.
- **Docs**: `docs/17d-payments.md` following the structure of
  `docs/17b-master-data.md`; this file's matrix updated afterward with the
  real completion percentage, not an estimate.

### Acceptance criteria

- Record a customer payment against a real invoice; invoice outstanding
  balance decreases correctly; journal entry posts correctly (debit
  cash/bank, credit AR).
- Record a vendor payment against a real bill; same effect, AP side.
- Partial payment leaves the invoice/bill partially outstanding, not
  auto-closed.
- Overpayment recorded as unallocated credit, not rejected, not silently
  dropped.
- Payment RLS-isolated per company, verified against real `erp_app`
  (own/cross-company SELECT/UPDATE/INSERT, missing-context default-deny —
  same test shape as `tests/test_rls_enforcement.py`).
- Full 130+N backend suite passes; `tsc`/`eslint`/`next build` clean.
- Final verification report follows the 19-item structure from the
  continuation directive, and this file's matrix is updated afterward.
