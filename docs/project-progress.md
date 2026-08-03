# Project Progress — Master Status Document

**This file is the authoritative, living record of where the ERP system
actually stands.** It is rebuilt from direct repository inspection each
time it's updated — never from memory of prior reports, and never from
what a phase name implies. Every completion percentage below is backed by
a specific file, endpoint, table, or test cited inline; a percentage with
no evidence next to it is a bug in this document, not a fact about the
project.

**Last verified**: 2026-08-04, on top of committed `d37661a` (`main`) —
the **Settings Architecture Foundation (Company Settings + Security/
Roles & Permissions)** milestone, uncommitted at time of writing —
183/183 backend tests, `ruff`/`tsc`/`eslint`/frontend production build
all clean, full live browser verification against a freshly-bootstrapped
company (real grant/revoke of a permission on an already-existing role,
confirmed to take effect immediately with no logout). See the dated
entry below for full detail. The paragraphs further below (2026-08-03
Entity Media Foundation and earlier) are kept verbatim as the historical
record and were not re-verified as part of this pass.

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
| **Master Data** | Phase 17B | Product (category+UOM+cost now exposed), ProductCategory tree, UnitOfMeasure, Partner — full CRUD+RLS+UI, best-covered area for permission-gating and error/empty states | 🟢 88% | `docs/17b-master-data.md`; 21 tests; frontend audit: only area with consistent `Can` gating AND explicit 404-vs-error distinction | no relation tabs on Product/Partner cards yet (Inventory/Sales/Purchase history — deferred by design comment), no bulk import/export |
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
