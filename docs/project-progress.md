# Project Progress — Master Status Document

**This file is the authoritative, living record of where the ERP system
actually stands.** It is rebuilt from direct repository inspection each
time it's updated — never from memory of prior reports, and never from
what a phase name implies. Every completion percentage below is backed by
a specific file, endpoint, table, or test cited inline; a percentage with
no evidence next to it is a bug in this document, not a fact about the
project.

**Last verified**: 2026-08-04, on top of committed `5aee470` (`main`) —
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
