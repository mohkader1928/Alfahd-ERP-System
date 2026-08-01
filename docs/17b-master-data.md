# Phase 17B — Master Data & Product Classification

Status legend: **IMPLEMENTED** · **DEFERRED TO 17E/17F/17H** (explicitly out
of this phase's scope, listed so it isn't silently forgotten).

---

## 1. Scope

Product Categories (hierarchical), Units of Measure (new), Product master
standardization (category/UOM/cost_price exposure), Customer/Vendor master
data (address, update capability), and a dedicated Master Data UI section
replacing the old flat `/admin` page — built entirely on Phase 17A's
shared component library (`ERPListView`, `FilterBar`, `FormView`,
`RecordCard`, `Breadcrumbs`, `Can`, `ConfirmDialog`).

## 2. Architecture

Unchanged from the existing project convention: Route → Service →
Repository → Model, all within the Identity module (`ProductCategory` and
the new `UnitOfMeasure` are company-scoped master data referenced by
Sales/Purchasing/Inventory, same as `Partner`/`Product`). `company_id` is
never accepted from the client — every create/update service method takes
it from `AuthContext`, and no request schema exposes it as a writable
field.

## 3. Database changes

**New table `unit_of_measure`**: `id`, `company_id NOT NULL`, `name`,
`name_ar` (nullable), `code`, `active BOOLEAN NOT NULL DEFAULT true`,
`created_at`, `updated_at`. Unique `(company_id, code)`. RLS: `ENABLE` +
`FORCE ROW LEVEL SECURITY` + `company_isolation` policy, identical pattern
to every other company-scoped table in this codebase.

**`product.uom_id`**: new nullable FK to `unit_of_measure.id`, indexed.
Verified safe pre-migration: 502 existing `product` rows, 0
`product_category` rows — a nullable column addition cannot violate
anything.

**`product_category`**: **no schema change**. Its RLS (`ENABLE`/`FORCE`/
`company_isolation`) already existed from the Phase 6/M2 migration
(`f81e8530ddbd`) — confirmed by inspection before writing any migration,
per the explicit instruction not to recreate it.

Migration: `a3f6e2c9d1b4_phase17b_uom_and_product_uom.py`, chained off
`0e71cd2ec945`. Verified reversible (`alembic downgrade -1` then
`upgrade head` both succeeded cleanly against the live dev database
before any application code was written against it).

## 4. Product Category

Flat CRUD (`GET/POST /product-categories`, `GET/PATCH/DELETE
/product-categories/{id}`) — hierarchy is expressed purely through
`parent_id`; the frontend assembles the tree client-side from one flat
list (no N+1, no recursive query).

Validation (service layer, `ProductCategoryService`):
- Empty name rejected.
- Parent must exist and belong to the caller's company.
- Self-parent rejected.
- Circular hierarchy rejected (ancestor-walk from the proposed parent;
  bounded so pre-existing bad data can't loop forever).
- Duplicate name among siblings (same `parent_id` + `company_id`)
  rejected, case-insensitive — same name is allowed under a different
  parent or at root, since the check is sibling-scoped, not global.
- Delete blocked (422) if the category has child categories or any
  product still references it — checked via `count_children()` and
  `ProductRepository.count_by_category()` before the delete, never left
  to an FK constraint error to leak through.

## 5. Unit of Measure

`GET/POST /uom`, `GET/PATCH /uom/{id}` — **no DELETE endpoint** (a
deliberate decision: deactivation via `PATCH .../active=false` is the
only lifecycle operation, so `product.uom_id` can never dangle). Code
uniqueness is case-insensitive and company-scoped. Verified: deactivating
a UOM that's already assigned to a product leaves that product's
`uom_id` untouched (test: `test_deactivate_uom_does_not_break_existing_product_reference`).

No conversion engine — deliberately deferred (see §11); the model shape
(flat `code`/`name`/`name_ar`/`active`) leaves room for a future
`base_uom_id`/`ratio` pair without a breaking change.

## 6. Product master

`ProductOut` now exposes `category_id`, `uom_id`, and `cost_price` (all
three existed on the model but were invisible through the API before
this phase — the exact gap the Phase 17 blueprint flagged). New `GET
/products/{id}` and `PATCH /products/{id}`; `GET /products` gained
`category_id` and `search` filters.

`ProductService` validates `category_id`/`uom_id` belong to the caller's
company on both create and update (rejecting a cross-company id with
422, not a raw FK error).

**Barcode and min/max/reorder fields: not added.** Confirmed absent from
the model before this phase, and explicitly classified P1/P2 (not P0) in
the Phase 17 blueprint — deferred to Phase 17F per this phase's own scope
instructions, not silently expanded into.

## 7. Partner master (Customer/Vendor)

`PartnerOut` now exposes `cr_number`, `address`, and a derived `is_active`
(computed from the existing `deleted_at IS NULL` — no new column, since
no delete/deactivate endpoint was requested for Partner this phase). New
`GET /partners/{id}` and `PATCH /partners/{id}`; `GET /partners` gained a
`search` param (matches name/name_ar/vat_number/cr_number).

**Address shape**: `partner.address` (and `branch.address`) were bare
`dict | None` JSONB columns with **no established shape anywhere in the
codebase** — grepped models, routes, schemas, tests, seed data; never
populated, never read. This phase defines the first shape:
`{street, city, region, postal_code, country_code}`, per the approved
minimal structure — not a pre-existing contract being preserved, a new
one being introduced.

No new Partner fields invented beyond what was explicitly approved
(no payment terms, no credit limit — those are Phase 17E territory).

## 8. API surface (new/modified, all under `/api/v1/identity`)

| Method | Path | |
|---|---|---|
| GET/POST | `/product-categories` | New |
| GET/PATCH/DELETE | `/product-categories/{id}` | New |
| GET/POST | `/uom` | New |
| GET/PATCH | `/uom/{id}` | New |
| GET/PATCH | `/partners/{id}` | New |
| GET | `/partners` | Modified — `search` param added |
| GET/PATCH | `/products/{id}` | New |
| GET | `/products` | Modified — `category_id`/`search` params added |

## 9. Permissions

New codes, seeded into `PERMISSION_CATALOG` and granted to every
company's bootstrap admin role like every other permission:
`product_category.view`, `product_category.manage`, `uom.view`,
`uom.manage`, `product.update`, `partner.update`. No RBAC architecture
change — same `require_permission()` dependency pattern as every existing
endpoint. Role-management UI remains Phase 17H, untouched.

## 10. Security / RLS — including one critical finding

Every mandated check was run and passed, **except one that surfaced a
pre-existing, session-wide gap**:

**Finding**: the `erp` Postgres role is a **superuser**
(`rolbypassrls = true`). Postgres superusers always bypass Row-Level
Security — `FORCE ROW LEVEL SECURITY` only binds non-superuser table
owners. This means **RLS has never actually been enforced at the database
layer in this dev environment**, for any table, in any phase — including
Phase 16A's. It was only ever caught here because this phase's new
`GET /partners/{id}` / `GET /products/{id}` routes were the first code
paths to rely on RLS *alone* (no explicit `company_id` filter) for
isolation; every prior isolation test happened to pass because the
application-layer queries it exercised (list endpoints, mostly) already
filter by `company_id` explicitly, independent of RLS.

**Fix applied in this phase**: both new GET routes, and the `update_partner`/
`update_product` service methods, now explicitly check
`row.company_id == ctx.company_id` after fetching by id — not relying on
RLS. This closes the gap for all Phase 17B code regardless of the
superuser issue. `ProductCategoryRepository`/`UnitOfMeasureRepository`
were written with explicit `company_id` filters from the start and were
never affected.

**Not fixed in this phase**: the underlying superuser/`BYPASSRLS`
configuration itself. Changing a database role's privilege bit is an
infrastructure-level change outside "master data" scope, and revoking
superuser needs its own careful verification pass (migrations, the
seeding lifecycle, and every other module all currently assume this
role's privileges) — recommended as a dedicated follow-up, analogous to
Phase 16A/16B, not something to bury inside this diff.

Verified regardless (via the fixes above and the new test suite):
Company A cannot read Company B's categories, UOMs, partners, or
products (list or direct-id GET); cannot modify them; cannot assign a
Company B category or UOM to a Company A product (422, not a leaked FK
error).

## 11. UI screens

New **Master Data** nav group (replacing the old flat "Administration →
`/admin`" entry): Products, Product Categories, Units of Measure,
Customers, Vendors.

- `/master-data/products` — `ERPListView`, category filter, category-path
  column, search.
- `/master-data/products/new`, `/master-data/products/[id]` — `FormView`
  / `RecordCard` (one real "Overview" tab — Inventory/Sales/Purchases/
  Accounting tabs are the future Product Card, not built here since
  there's no real data to show in them yet).
- `/master-data/categories` — dedicated tree UI (expand/collapse,
  add-root/add-child/edit/delete via `ConfirmDialog`), new page-local
  component (not promoted to the shared library — no second consumer
  yet).
- `/master-data/uom` — inline create form + `ERPListView` list, same
  pattern as the existing Chart-of-Accounts tab for small lookup tables.
- `/master-data/customers`, `/master-data/vendors` — both render the new
  shared `PartnerListView` component (parameterized by `kind`), per the
  explicit "don't duplicate" instruction.
- `/master-data/partners/new`, `/master-data/partners/[id]` — create form
  and `RecordCard`-based edit view with the new Address section.
- New shared `components/erp/category-select/` — nested/indented category
  picker showing the full path ("Electrical / Lighting / LED Panels"),
  used by both the Product form and the Category form's parent field;
  excludes a category's own descendants when editing it (matching the
  backend's cycle guard at the UI level too).

`/admin/page.tsx` **deleted** — its two sections (Partners, Products)
are fully superseded (list + create + edit + search + filter, where the
old page had create + flat list only).

## 12. Validation summary

Category: empty name, invalid/cross-company/self/circular parent,
duplicate sibling name, delete-with-dependents — all rejected with 422,
never a raw database error. UOM: empty name/code, duplicate code
(case-insensitive), cross-company — all 422. Product: cross-company
category/UOM rejected 422; existing SKU-uniqueness and price handling
preserved unchanged. Partner: existing customer-or-vendor requirement
preserved on both create and update.

## 13. Tests

New file `backend/tests/test_master_data_categories_uom.py` — 33 tests,
all passing: category CRUD/hierarchy/duplicate/deletion-guards/isolation
(12), UOM CRUD/deactivation/duplicate/isolation (7), product category+UOM
assignment/update/filter/cross-company (8), partner
create/update/address/isolation (6). Every new tenant-owned surface
(category, UOM, product's new fields, partner's new fields) has at least
one genuine cross-company isolation test using two real bootstrapped
companies over real HTTP against real Postgres — no mocks.

Authorization coverage is HTTP-level "no token → 401" only (one test per
new resource) — genuine non-admin permission-denial testing isn't
possible today because no endpoint anywhere creates a *restricted* role
(only bootstrap's full-access admin role exists); noted as a real gap,
not silently skipped.

**Full regression**: 100/100 passed (67 pre-existing + 33 new), run
three times across this phase (before frontend work, after, and again
after the Docker cold restart) — zero regressions at any point. Ruff
clean throughout.

## 14. Known limitations / deferred items

- Barcode, min/max/reorder-level fields — **Phase 17F**.
- The RLS-bypass-via-superuser finding (§10) — recommended as its own
  dedicated hardening phase, not fixed here.
- Product/Customer/Vendor "360" card (balances, statements, history
  tabs) — **Phase 17E**, depends on Payments (17C).
- RBAC role-management UI — **Phase 17H**.
- UOM conversion engine — not started; model shape leaves room for it.
- Category tree component — page-local, not promoted to the shared
  `components/erp/` library (no second consumer yet to justify it).
- Frontend automated tests: none exist in this repo (confirmed — no test
  runner is configured); all frontend verification in this phase was
  live browser verification against the real API, documented in the
  final report, not claimed as automated coverage.
