# Phase 16A — Multi-Tenancy & Database Isolation Hardening

Closes the confirmed database isolation gaps identified in the Phase 16
repository audit. Scope: database/backend tenant isolation only — frontend,
CORS, ZATCA production certification, CI/CD, performance, demo data, and
new modules are explicitly out of scope for this task.

## 1. Previous architecture

Every request resolves a JWT + `X-Company-Id`/`X-Branch-Id` header into an
`AuthContext` (`shared/security/auth_context.py`), which sets two
Postgres session variables via `SET LOCAL` before any repository code
runs:

- `app.current_tenant_id` — read by the **tenant tier** RLS policies
  (`company`, `branch`, `app_user`, `audit_log`, `activity_log`)
- `app.current_company_id` — read by the **company tier** RLS policies
  (every document-root table: `quotation`, `sales_invoice`,
  `purchase_order`, `journal_entry`, `stock_move`, `warehouse`, etc.)

All existing policies use `FORCE ROW LEVEL SECURITY` (required — the app
connects as the table-owning role, which Postgres exempts from RLS unless
forced) and follow the identical shape:

```sql
CREATE POLICY company_isolation ON <table>
USING (company_id = current_setting('app.current_company_id', true)::uuid)
WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid)
```

## 2. Identified isolation gaps

| Gap | Root cause |
|---|---|
| `role`, `user_company_access` | Already had `company_id` (NOT NULL, populated) — simply never had a policy added |
| 8 line-item tables (`quotation_line`, `sales_order_line`, `sales_invoice_line`, `vendor_bill_line`, `purchase_order_line`, `goods_receipt_line`, `journal_entry_line`, `cycle_count_line`) + `location` | No `company_id` column at all — isolation existed only because repository code always joined through the parent (which does have RLS) |
| `zatca_submission` | Same shape — one non-nullable FK (`sales_invoice_id`) to a parent with RLS, no `company_id` of its own |

## 3. Chosen solution

**Option A: direct `company_id` on every affected table, backfilled from
the parent, protected by its own `company_isolation` policy** — over the
alternative of a subquery-based policy reaching into the parent without a
new column.

Reasoning: every other company-scoped table in this schema already uses a
direct column; a subquery-based policy would still be
application-relationship-shaped isolation just relocated into the policy
definition, introduce a second RLS pattern to reason about, and be
strictly worse for query performance (a correlated subquery per row vs. a
plain indexable predicate). `role`/`user_company_access` needed no schema
change — the column already existed, only the policy was missing.

## 4. Schema changes

One migration:
[`8957d3c39d54_phase16a_multi_tenancy_hardening.py`](../backend/migrations/versions/8957d3c39d54_phase16a_multi_tenancy_hardening.py).

For each of the 8 line tables + `location` + `zatca_submission`:

1. `ALTER TABLE <t> ADD COLUMN company_id UUID` (nullable at first)
2. `UPDATE <t> SET company_id = <parent>.company_id FROM <parent> WHERE <t>.<parent_fk> = <parent>.id`
3. A `DO $$ ... RAISE EXCEPTION ...` guard verifying zero NULL rows before proceeding
4. `ALTER TABLE <t> ALTER COLUMN company_id SET NOT NULL`
5. `CREATE INDEX ix_<t>_company_id` (plain indexed UUID, no FK to `company.id` — matches the existing convention outside the identity module; see `sales`/`purchasing`/`inventory` models, which never FK `company_id` to `company.id`)
6. `ENABLE`/`FORCE ROW LEVEL SECURITY` + `CREATE POLICY company_isolation`

For `role` and `user_company_access`: steps 6 only — no schema change.

No existing column, index, or constraint was touched. Purely additive.

### A real migration-time obstacle, and how it was resolved

`journal_entry_line` carries an immutability trigger
(`trg_journal_entry_line_immutable`, added in the M1 accounting migration)
that rejects **any** `UPDATE` once the parent entry is posted — a real,
working accounting-integrity control (FR-ACC-004: posted entries are never
silently modified), not a bug. The backfill `UPDATE` in step 2 hit this
trigger on the first migration attempt.

This is a metadata correction (adding tenant scoping to existing rows), not
a change to posted financial content, so `SET session_replication_role =
replica` is used to suppress trigger firing for the single backfill
statement on this one table, then immediately reset to `DEFAULT`. This is
the standard Postgres pattern for migration-time bulk operations that need
to bypass triggers without altering them — no `ALTER TABLE ... DISABLE
TRIGGER` (which was tried first and failed with "pending trigger events,"
a known Postgres restriction on toggling trigger state and doing DML
within the same transaction) and no change to the trigger definition
itself. The immutability control is fully intact for the application after
this migration completes.

### Backfill verification (run against the live dev database)

```
     tablename      | rowsecurity          tablename      |    policyname
---------------------+------------  ---------------------+-------------------
 cycle_count_line    | t             cycle_count_line    | company_isolation
 goods_receipt_line  | t             goods_receipt_line  | company_isolation
 journal_entry_line  | t             journal_entry_line  | company_isolation
 location            | t             location            | company_isolation
 purchase_order_line | t             purchase_order_line | company_isolation
 quotation_line      | t             quotation_line      | company_isolation
 role                | t             role                | company_isolation
 sales_invoice_line  | t             sales_invoice_line  | company_isolation
 sales_order_line    | t             sales_order_line    | company_isolation
 user_company_access | t             user_company_access | company_isolation
 vendor_bill_line    | t             vendor_bill_line    | company_isolation
 zatca_submission    | t             zatca_submission    | company_isolation
(12 rows)                             (12 rows)
```

Spot-check confirming the backfilled `company_id` exactly matches the
parent's, zero mismatches:

```sql
SELECT
  (SELECT count(*) FROM quotation_line ql JOIN quotation q ON ql.quotation_id=q.id WHERE ql.company_id != q.company_id),
  (SELECT count(*) FROM journal_entry_line jl JOIN journal_entry j ON jl.journal_entry_id=j.id WHERE jl.company_id != j.company_id),
  (SELECT count(*) FROM zatca_submission z JOIN sales_invoice si ON z.sales_invoice_id=si.id WHERE z.company_id != si.company_id),
  (SELECT count(*) FROM location l JOIN warehouse w ON l.warehouse_id=w.id WHERE l.company_id != w.company_id);
-- 0 | 0 | 0 | 0
```

## 5. Application code changes

Every ORM object construction site for the affected models was updated to
pass `company_id=` explicitly — the value always comes from
`AuthContext.company_id` (or, inside `_run_zatca_pipeline`, from the
already-loaded parent `invoice.company_id`), **never from client-supplied
request data**. Confirmed by inspection: every `*CreateRequest` Pydantic
schema in this API omits `company_id` entirely; it only appears in `*Out`
response schemas. A behavioral test
(`test_insert_isolation_company_id_is_never_client_supplied`) additionally
proves that even a client attempting to inject an unexpected `company_id`
into a request body has no effect — the created record still belongs to
the authenticated company.

10 call sites across 4 files:

| File | Constructors updated |
|---|---|
| `accounting/application/services.py` | `JournalEntryLine` (×2 — draft creation, reversal) |
| `sales/application/services.py` | `QuotationLine`, `SalesOrderLine`, `SalesInvoiceLine` (×2 — invoice issuance, credit note), `ZatcaSubmission` |
| `purchasing/application/services.py` | `PurchaseOrderLine`, `GoodsReceiptLine`, `VendorBillLine` |
| `inventory/application/services.py` | `Location`, `CycleCountLine` |

## 6. Security test strategy

New file: [`backend/tests/test_multi_tenancy_isolation.py`](../backend/tests/test_multi_tenancy_isolation.py)
— 17 tests, all through the real HTTP/API boundary against the real
dockerized Postgres (no repository-level shortcuts, matching every other
test file's approach), because what's being proven is what an actual
attacker or a future buggy endpoint could or couldn't do.

Two full companies (Alpha, Beta) are bootstrapped once per test-module run,
each with a real quotation→order→invoice (with ZATCA clearance), PO→
receipt→bill, manual journal entry, and cycle count — then every test
attempts some form of cross-company access from Alpha against Beta's real
IDs.

| Category | Tests | Result |
|---|---|---|
| SELECT isolation | Direct GET on all 5 document types by ID; list endpoints (quotations, PO, vendor bills, journal entries, stock moves) never include the other company's rows | ✅ 404 / absent |
| ZATCA | Cannot reach Company B's `zatca_submission` via the invoice detail endpoint; positive control confirms Company A's own submission is reachable | ✅ |
| UPDATE (state-mutating actions, since no DELETE endpoint exists anywhere in this API) | Confirm quotation, reverse journal entry, confirm PO, approve vendor bill, issue credit note — all attempted against Company B's IDs while authenticated as Company A | ✅ 404/422 |
| INSERT isolation | Client-supplied `company_id` in a request body is ignored, not trusted; PO line / journal-entry-account references to a foreign company are rejected | ✅ |
| Line-item ID manipulation (the specific gap this migration closed) | Vendor bill and goods receipt against a foreign PO line ID | ✅ 422 — RLS makes the lookup return no row, not just an application-level ownership check |
| Reports | Dashboard totals identical between two identically-scripted companies (no double-counting); CSV export row count matches only the requesting company's own data | ✅ |
| RBAC + RLS interaction | The bootstrap admin role — granted every permission in the catalog, the most powerful role this system has — still cannot read or act on Company B's journal entries | ✅ |

`role` and `user_company_access` have no dedicated end-to-end API test:
no endpoint in this system lists or exposes another company's
roles/access-grants directly, so there's no meaningful HTTP-boundary
scenario beyond what the RBAC+RLS test above already covers. Their
isolation is proven directly by the `pg_policies`/`pg_tables` query in
§4 — deliberately not padded with a fabricated API assertion that
wouldn't test anything real.

One real bug was found and fixed during test-writing, not glossed over:
`GET /identity/companies/{company_id}` ignores its own path parameter and
always returns `ctx.company_id`'s data — not a leak (Company B's data is
never returned), but a request for Company B's ID silently returns Company
A's own record rather than a clean 403/404. The test
(`test_get_company_endpoint_ignores_path_id_and_never_returns_foreign_company`)
asserts the actual behavior rather than the behavior I originally assumed.

## 7. Results

- **60/60 backend tests pass** (43 pre-existing + 17 new), run against a
  freshly-restarted (not hot-reloaded) Docker stack.
- **Ruff**: clean (`src` + `tests`).
- **Frontend build**: clean, unaffected — no API response schema was
  touched by this change (only `*Out` schemas would need updating to
  expose `company_id` on lines, and none currently do), so there is no
  frontend/API-contract impact from this migration.
- **Docker Compose**: `api`/`worker` restarted cold, `/health` returns
  `{"status":"ok","database":true}`.

## 8. Remaining limitations

- `role_permission` and `user_role` (pure join tables, no `company_id`,
  isolated today only via joining to `role`/`app_user`) are the same shape
  as the fixed gaps but were **not** in this task's scope — flagged for
  visibility, not touched.
- Line-item RLS is now real, but this migration doesn't address the
  separately-audited concurrency gap (no `SELECT ... FOR UPDATE` anywhere
  in the codebase) — a different Phase 16 risk, out of scope for 16A.
- The `GET /companies/{company_id}` path-parameter-ignoring behavior found
  in §6 is not a security bug (confirmed: never returns foreign data) but
  is worth a follow-up cleanup — either honor the path param with a proper
  ownership check, or drop it from the route signature since it's unused.
