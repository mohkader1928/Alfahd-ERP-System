# Phase 16B — Idempotency & Concurrency Hardening: Design & Audit

**Status: design document only.** No application code, migrations, or tests
were written for this phase — every finding below was verified directly
(by reading the actual code and querying the live database's catalogs),
not assumed from the presence or absence of `SELECT ... FOR UPDATE` in the
source.

---

## Executive Summary

This audit found one **critical, deterministically-reproducible bug**
(not a rare race — a guaranteed duplicate on any retry), one **real
lost-update race condition** with no database backstop, and several
**secondary races** that are partially mitigated by existing constraints
but not fully closed. It also found the codebase already does several
things right that don't need touching.

**The single most important finding**: issuing a sales invoice
(`POST /sales/orders/{id}:invoice`) never advances the sales order's
status. Calling this endpoint twice — for *any* reason, including a
plain client retry after a network timeout, with no concurrency involved
at all — creates two complete invoices, two journal entries (double
revenue recognition), two ZATCA submissions, and two stock deductions.
This is exactly the scenario named in the task's §6 conceptual test, and
the answer is a confirmed **yes, the server creates a second invoice.**

**What's already correct and doesn't need touching**: the single-
transaction-per-request architecture, the `company_isolation` RLS from
Phase 16A working correctly alongside these concerns, quotation and
purchase-order confirmation (both properly flip status and correctly
block re-confirmation), and the goods-receipt/vendor-bill cumulative
quantity bounds (which self-heal against *sequential* retries, even
though they remain open to *true concurrent* races).

---

## Current Transaction Architecture

Traced directly from `shared/infrastructure/db/session.py`,
`shared/security/auth_context.py`, and every module's `api/routes.py`:

- `get_db()` yields one `AsyncSession` per request (function-scoped
  FastAPI dependency) — no `async with session.begin()` wrapper; a
  transaction begins implicitly on the first statement.
- `AuthContext` resolution (`get_auth_context`) runs `SET LOCAL
  app.current_tenant_id` / `app.current_company_id` on that same session,
  before any repository code executes — this is also, incidentally, why
  the RLS context is guaranteed to apply to every statement in the
  request: it's the same transaction throughout.
- **Every `await db.commit()` in the entire backend lives in an
  `api/routes.py` file** — confirmed by grep across all five modules; zero
  commits inside `application/services.py`. This means each HTTP request
  is exactly one transaction: all repository/service calls within a route
  handler share one atomic unit, and an unhandled exception before commit
  leaves the session's `async with` block to close without committing
  (SQLAlchemy rolls back automatically on exit-without-commit).
- **No isolation level is explicitly set anywhere** — the engine
  (`create_async_engine`) and session (`async_sessionmaker`) use
  SQLAlchemy/asyncpg defaults, which is Postgres's default: **READ
  COMMITTED**. This matters directly: READ COMMITTED does not prevent two
  concurrent transactions from both reading the same "before" state and
  both computing conflicting "after" states — the classic lost-update
  shape found repeatedly below.
- **Zero occurrences of `SELECT ... FOR UPDATE` anywhere in the
  codebase** (confirmed by grep) — this is stated as fact here because it
  was directly verified, not because its absence alone implies a problem;
  several places genuinely don't need it (see §"What's Already Correct").

---

## Document Numbering Findings

Every numbered document (`Quotation`, `SalesOrder`, `SalesInvoice`,
`PurchaseOrder`, `GoodsReceipt`, `VendorBill`) uses the identical pattern,
verified in each repository:

```python
async def next_number(self, company_id: UUID) -> str:
    result = await self.session.execute(select(func.count()).where(Table.company_id == company_id))
    count = result.scalar_one()
    return f"PREFIX-{count + 1:06d}"
```

This is a **non-locking read** (`SELECT count(*)`) followed by an INSERT
in the same transaction. Two concurrent requests for the same company can
both count *N* existing rows and both compute *N+1* — this is a real race,
confirmed by tracing the code, not assumed.

**What actually happens when it fires** — verified directly against
`pg_constraint`:

| Table | `UNIQUE(company_id, number)`? | Consequence of the race |
|---|---|---|
| `quotation`, `sales_order`, `sales_invoice`, `purchase_order`, `vendor_bill` | ✅ Yes | The **losing** concurrent request gets a raw `IntegrityError`, surfacing as an unhandled `500` (there is no `try/except` translating it to a clean `409` — same gap already noted for `Company.vat_number` in the existing `test_duplicate_vat_number_rejected` test). No silent duplicate number is possible. |
| `goods_receipt` | ❌ **No constraint exists** | **Genuinely missing.** A concurrent race here can silently create two `GoodsReceipt` rows with the identical `number` — confirmed by direct `pg_constraint` query; this is the one place a duplicate document number is not just theoretically possible but has zero backstop. |

Journal entries have no sequential `number` field at all (`reference` is
free-text, supplied by the caller) — there is no numbering race to close
for accounting entries specifically.

**Skipped numbers** (the losing request's number simply isn't used) are
an acceptable, normal outcome for business document numbering — the
concern is duplicates, not gaps.

---

## Inventory Concurrency Findings

**`stock_quant.qty_on_hand` — confirmed lost-update race, no backstop.**
Traced exactly, in `inventory/application/services.py`:

```python
quant = await self.quant_repo.get_or_create(company_id, product_id, location_id)  # plain SELECT, no lock
...
quant.qty_on_hand -= qty   # mutated in Python memory
...
# flush() later issues: UPDATE stock_quant SET qty_on_hand = <computed value> WHERE id = ...
```

This is an **absolute write of a Python-computed value**, not an atomic
`SET qty_on_hand = qty_on_hand - :delta`. Walking through the task's own
example precisely:

1. Product X has `qty_on_hand = 10`.
2. Request A (`issue 8`) and Request B (`issue 7`) both call
   `get_or_create` before either commits — both read `10`.
3. Both pass the insufficient-stock check locally (`10 >= 8` and
   `10 >= 7` are each individually true from each request's stale view).
4. Whichever commits first writes `10 - 8 = 2`. The second commits
   *after*, overwriting with `10 - 7 = 3` — **the first deduction is
   silently lost**, and the final value (`3`) is wrong under every
   interpretation: it's neither the correct combined result (which should
   have been rejected, since only 2 units remained after A) nor a
   faithful record of either individual operation.

**Confirmed asymmetry via direct `pg_constraint` query**:
`stock_layer.qty_remaining` has `CHECK (qty_remaining >= 0)` — a real
database backstop. **`stock_quant.qty_on_hand` has no equivalent check.**
So even in the "negative stock" framing from the task (`10 - 8 - 7 = -5`),
the *aggregate* on-hand quantity has no database-level protection at all;
only the FIFO layer detail table does.

**FIFO layer consumption** (`layer_by_id[layer_id].qty_remaining -=
qty_consumed`) has the identical read-into-Python-then-flush shape, and
is subject to the same class of lost update between concurrent issues
against the same product/location — the `CHECK` constraint would catch an
individual layer going *negative*, but not two concurrent partial
consumptions silently overwriting each other while both staying
individually non-negative.

**Multiple lines in one document, same product**: since the whole
document (e.g., a multi-line sales invoice) runs in one transaction and
`quant` objects are tracked by SQLAlchemy's identity map, two *lines*
referencing the same product within the *same* request correctly
accumulate in memory (no race with itself) — the risk is strictly
cross-request.

---

## Accounting Concurrency Findings

**`post_entry` double-post race — confirmed present, but low severity.**
Traced in `accounting/application/services.py`:

```python
entry = await self.entry_repo.get_by_id(entry_id)          # no lock
if entry.status == "posted": raise PostedEntryImmutableError(...)
...
entry.status = "posted"
entry.posted_at = _utcnow_naive()
entry.version += 1
```

Two concurrent `POST /journal-entries/{id}:post` calls for the same entry
could both read `status == "draft"` before either commits, and both
proceed. **This does not duplicate any financial effect** — `post_entry`
only flips a status flag and re-validates the balance on lines that
already exist; it does not create new lines or a new entry. The one real
casualty is `entry.version` — both requests would compute `version + 1`
from the same stale read, so the increment itself is a lost update (the
field isn't currently used anywhere as an optimistic-concurrency check,
so this is a data-quality nit, not a financial risk). **Not prioritized
for locking** — see the Implementation Order.

**Reversal** (`reverse_entry`) has the same status-check shape and the
same low-severity conclusion — it also only reads the *existing* lines
to build a reversal, so a double-reversal race would create two reversal
entries, which *is* a real financial duplication risk, just lower
likelihood than the invoice-retry bug since reversal is a deliberate,
infrequent admin action rather than something naturally retried by a
client after a timeout.

**The real financial risk is not in `post_entry` — it's upstream, in
whatever creates and posts an entry as one action** (see next section).

---

## Critical Race Conditions (ranked)

1. **[CRITICAL — not actually a race, a deterministic bug] Sales invoice
   issuance has no idempotency guard of any kind.** `issue_invoice_from_order`
   reads `order.status` but — confirmed by grepping every occurrence of
   `order.status` in `sales/application/services.py` — **never writes
   it**. The order stays `"confirmed"` forever, even after a successful
   invoice. Calling `POST /orders/{id}:invoice` twice, sequentially, with
   zero concurrency involved, creates:
   - a second `SalesInvoice` row (own number, since numbering doesn't
     collide across genuinely sequential calls)
   - a second journal entry — **double revenue recognition**
   - a second `ZatcaSubmission`, chained onto the hash chain with a new
     ICV — a real compliance problem, not just a bookkeeping one
   - a second stock deduction via `_deduct_stock_for_lines`, silently
     removing twice the inventory that was actually sold
   This is exactly the task's §6 test scenario, and the honest, verified
   answer is: **yes, the server creates a second invoice.**

2. **[HIGH] `stock_quant.qty_on_hand` lost-update race** — see Inventory
   Findings above. Real under genuine concurrent load (two warehouse
   staff, or two channels, acting on the same product near-simultaneously).

3. **[MEDIUM] ZATCA ICV sequencing race.**
   `latest_zatca_submission_for_company` (used by
   `_next_icv_and_previous_hash`) is a plain `SELECT ... ORDER BY icv DESC`
   with no lock. Two concurrent invoice issuances for the *same company*
   (which, given finding #1, is now a plausible trigger — a rapid double-
   click hits both the invoice-duplication bug *and* this one
   simultaneously) could compute the same next ICV, breaking the
   hash-chain's required total order — a ZATCA-compliance-relevant defect,
   not merely an internal bookkeeping one.

4. **[MEDIUM] Goods receipt / vendor bill cumulative-quantity race under
   true concurrency.** `po_line.qty_received + qty > po_line.qty` is
   checked against a value read at the start of the transaction, then
   written without a lock. Sequential retries are self-healing (each retry
   re-reads the post-commit state), but two genuinely simultaneous
   receipts against the same PO line are vulnerable to the same
   lost-update shape as stock_quant, potentially allowing over-receipt
   beyond what was ordered.

5. **[LOW] `goods_receipt` missing `(company_id, number)` unique
   constraint** — confirmed via direct catalog query; the one document
   type with zero backstop against a duplicate number.

6. **[LOW] Journal entry post/reverse double-post race** — see Accounting
   Findings; no duplicated financial effect for `post`, low-likelihood
   duplicated effect for `reverse`.

---

## What's Already Correct (verified, not assumed)

- **Quotation confirmation** (`confirm_to_sales_order`): checks
  `status != "draft"` *and* sets `quotation.status = "confirmed"` before
  returning — a genuine retry correctly gets rejected on the second call.
- **Purchase order confirmation** (`confirm_purchase_order`): same
  correct shape — status is both checked and written.
- **Journal entry immutability** (Phase 16A's finding, still true):
  `trg_journal_entry_line_immutable` blocks any edit to posted lines at
  the database level — a real backstop independent of application code.
- **Multi-tenancy RLS** (Phase 16A): every table discussed here already
  carries `company_id` + an active `company_isolation` policy, so any
  locking added in this phase is naturally company-scoped without extra
  work.
- **Redis is not used for anything beyond the Celery broker** — confirmed
  by grep (no caching, no application-level Redis client anywhere in
  `src/`). This directly supports the recommendation below: there is no
  existing Redis-based pattern this system would be fighting by choosing
  Postgres for idempotency.

---

## Idempotency Findings

**Zero idempotency mechanism exists anywhere** — confirmed by grep for
`Idempotency`/`idempotency_key`/`Idempotency-Key` across the entire
backend: no matches. No request-identifier handling, no idempotency
table, no header parsing.

**Conceptual retry-after-timeout test, run against the actual code path**:
> Request A creates an invoice. The server commits successfully but the
> client never receives the response (network timeout). The client
> retries the identical request.

**Result: the server creates a second, fully independent invoice** — see
Critical Race Condition #1. This is not a hypothetical; it's a direct
trace of `issue_invoice_from_order`'s actual logic.

---

## Proposed Idempotency Architecture

### Option comparison

| Option | Verdict |
|---|---|
| **A — bare `Idempotency-Key` stored in Postgres with no request-hash check** | Rejected: can't distinguish "the same retry" from "a different request that happens to reuse a key" — exactly the "same key + different payload" scenario the task requires detecting. |
| **B — full idempotency record (company/key/endpoint/request-hash/response/expiry) in Postgres** | **Recommended.** Matches this system's existing architecture: everything already flows through one Postgres transaction per request, RLS already scopes by `company_id`, and there is no existing Redis usage pattern to build on instead. |
| **C — DB unique constraints alone for "naturally unique" operations** | Already partially in place (document numbers) and **kept** — but insufficient alone, since it stops *duplicate numbers*, not *duplicate business operations retried under a fresh, correctly-unique number* (finding #1 proves a retry gets a valid new number every time). |
| **D — Redis-based idempotency** | Rejected as the source of truth, per the task's own instruction and because Redis isn't durable here (no persistence config inspected/assumed) and isn't currently used for anything beyond Celery transport — introducing it as a second source of truth for financial correctness would be new architectural surface for no compensating benefit over Postgres, which is already the transactional boundary for every one of these operations. |

**Decision: Option B, on Postgres**, using the SAME session/transaction
already open for the business operation — not a separate pre-check
transaction. This makes the idempotency record's commit atomic with the
business effect it's guarding, and — as a deliberate secondary benefit —
lets the idempotency row double as the concurrency-serialization point
(see Row-Locking Strategy).

### Proposed table

```sql
CREATE TABLE idempotency_key (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL,
    user_id         UUID NOT NULL,
    idempotency_key TEXT NOT NULL,
    endpoint        TEXT NOT NULL,        -- e.g. "POST /sales/orders/{id}:invoice"
    request_hash    TEXT NOT NULL,        -- sha256 of canonical (method, path, body)
    status          TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | completed | failed
    response_status INT,
    response_body   JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    expires_at      TIMESTAMP NOT NULL,   -- created_at + 24h, matching typical retry windows
    UNIQUE (company_id, idempotency_key, endpoint)
);
-- RLS: company_isolation policy, identical shape to every Phase 16A table.
```

`endpoint` is included in the uniqueness key deliberately: a client
should not be able to reuse one key across two logically unrelated
operations even by accident.

### Request flow (per protected endpoint)

1. Client sends `Idempotency-Key: <client-generated-uuid>`.
2. Handler computes `request_hash` from a canonical serialization of
   `(method, path, sorted-keys JSON body)` — using the *raw incoming*
   body, before any server-side defaulting, so the hash reflects what the
   client actually sent.
3. `SELECT ... FOR UPDATE` the row for `(company_id, key, endpoint)`
   within the request's existing transaction:
   - **No row found** → `INSERT ... status='in_progress'`, proceed to
     execute the business logic, then `UPDATE` the same row to
     `status='completed'` with the real response, all before the single
     `COMMIT` the route already issues.
   - **Row found, `request_hash` matches, `status='completed'`** →
     skip the business logic entirely; return the stored
     `response_status`/`response_body`. This is the "same key, same
     request" fast path — exactly one business operation ever happened.
   - **Row found, `request_hash` does not match** → `409 Conflict`,
     `"Idempotency-Key already used with a different request"`. No
     mutation.
   - **Row found, `status='in_progress'`** → because this is a
     `SELECT ... FOR UPDATE`, a genuinely concurrent second request
     *blocks* here until the first transaction resolves — it does not
     race past this point. Once unblocked, it re-reads the row: if the
     first request committed, it now sees `'completed'` and returns the
     stored response; if the first request rolled back (crashed,
     validation error, etc.), the row is gone (see below) or stale enough
     to retry.
4. On any business-logic failure, the idempotency row is not left in
   `'completed'` state — either the whole transaction rolls back (row
   disappears entirely, since the `INSERT` was part of the same
   transaction) or, if partial success needs to be preserved, marked
   `'failed'` so a retry is allowed rather than permanently blocked.
5. `expires_at` (24h) exists so the table doesn't grow unboundedly; a
   background cleanup (out of scope for this phase — flagged for 16C)
   deletes expired rows.

This single mechanism directly closes finding #1 (duplicate invoice on
retry) for every endpoint it's applied to, and simultaneously serializes
concurrent identical requests without a separate lock.

---

## Idempotency Scope — MUST / SHOULD / NOT REQUIRED

| Endpoint | Priority | Why |
|---|---|---|
| `POST /sales/orders/{id}:invoice` | **MUST** | Confirmed critical bug — no other guard exists at all. |
| `POST /sales/invoices/{id}:credit-note` | **MUST** | Same shape as invoice issuance — creates a new invoice-type row + journal entry + ZATCA submission with no status guard on the original invoice preventing re-issuance. |
| `POST /purchasing/orders/{id}/vendor-bills` | **MUST** | Real financial posting; existing cumulative-qty guard only protects sequential retries, not true concurrency. |
| `POST /purchasing/vendor-bills/{id}:approve` | **MUST** | Posts a journal entry (GRNI reversal + AP); status check exists but is the same "check-then-write, no lock" shape as `post_entry` — lower risk than invoice issuance but still a real posting action. |
| `POST /accounting/journal-entries` (manual creation) | **SHOULD** | Direct financial entry; less likely to be blindly retried by a UI (no natural "resume" trigger like a network timeout on a single button), but still money. |
| `POST /purchasing/orders/{id}/goods-receipts` | **SHOULD** | Inventory + GRNI impact; cumulative-qty guard already gives meaningful sequential-retry protection, so this is "should" rather than "must." |
| `POST /inventory/stock/receive` | **SHOULD** | Direct inventory impact; no natural document-level guard at all today. |
| `POST /inventory/transfers` | **SHOULD** | Same reasoning as stock receive. |
| `POST /sales/quotations` | NOT REQUIRED | Draft-only, no accounting/inventory/ZATCA effect; a duplicate quotation is a UX annoyance, not a financial or compliance problem. |
| `POST /purchasing/orders` (create) | NOT REQUIRED | Same reasoning — draft PO creation has no downstream effect until confirmed. |
| `POST /sales/quotations/{id}:confirm` | NOT REQUIRED | Already correctly guarded — status check *and* write both present, verified. |
| `POST /purchasing/orders/{id}:confirm` | NOT REQUIRED | Same — already correctly guarded. |
| `POST /accounting/journal-entries/{id}:post` | NOT REQUIRED | Idempotent by nature (flips a status flag, `PostedEntryImmutableError` already blocks the meaningful case); row-locking (below) is the right fix here, not idempotency-key machinery. |
| `POST /inventory/cycle-counts` | NOT REQUIRED | Creates a draft count for review, not a posted financial/inventory effect on its own. |
| Every `GET` endpoint | NOT REQUIRED | Naturally idempotent by HTTP semantics; the task explicitly warns against blanket-applying this to reads. |

---

## Proposed Row-Locking Strategy

| Target | Lock | Duration | Why | Index support |
|---|---|---|---|---|
| `stock_quant` row for `(product_id, location_id)` | `SELECT ... FOR UPDATE` at the start of `receive_stock`/`issue_stock`, before reading `qty_on_hand` | For the remainder of that one transaction (a handful of statements — milliseconds under normal load) | Closes the lost-update race directly at its source | `ux_stock_quant_product_location` already covers this exact lookup — no new index needed |
| `stock_layer` rows consumed during FIFO issue | Lock via the *parent* `stock_quant` row above, not each layer individually | Same transaction | Layers are only ever read/written in service of one quant's issue operation; locking the quant is sufficient to serialize layer consumption for that product+location without a second lock | `ix_stock_layer_fifo` already supports the ordered read |
| `purchase_order_line` row(s) being received/billed | `SELECT ... FOR UPDATE` on the specific line(s) before reading `qty_received`/`qty_billed` | Same transaction | Closes the concurrent-receipt/bill race | Primary key lookup — no new index needed |
| Idempotency row | `SELECT ... FOR UPDATE` (see above) | Same transaction as the guarded operation | Doubles as the per-key serialization point | `UNIQUE (company_id, idempotency_key, endpoint)` already supports this |

**Explicitly not locking**: `journal_entry`/`journal_entry_line` for
`post`/`reverse` (low severity, see Accounting Findings — a status-guard
fix is sufficient there, not a lock), and document-number generation
(fixed via a proper atomic counter instead of a lock — see Database
Constraints below).

**No table-level locks anywhere in this proposal** — every lock is a
single-row `FOR UPDATE`, matching the task's explicit instruction.

---

## Transaction Boundaries — per critical operation

Using invoice issuance as the worked example (the highest-priority fix):

1. Request enters `POST /sales/orders/{id}:invoice`.
2. `AuthContext` resolved, RLS session variables set (already correct today).
3. Transaction implicitly begins on first statement (already correct).
4. **[current gap]** `order` is read with no lock — **fix: `SELECT ... FOR
   UPDATE` on the order row**, so a concurrent/retried second request
   blocks here rather than racing past the status check.
5. Idempotency row checked/inserted (new, per above) — inside the same
   transaction, using the same lock semantics.
6. Business validation (`order.status == "confirmed"`, stock sufficiency).
7. Invoice + lines written.
8. Journal entry written and posted; stock deducted (accounting/inventory
   effects) — **already inside the same transaction today**, this part
   is correct.
9. **[current gap]** `order.status` is never advanced — **fix: set it**
   (e.g., to `"invoiced"` or reuse `"done"`, a design choice for
   implementation, not this doc).
10. Idempotency row updated to `'completed'` with the response payload.
11. Single `COMMIT` (already correct — the route's existing one commit
    point doesn't need to move).
12. Response returned; ZATCA async-reporting task enqueued *after* commit
    (already correct today — the code deliberately does this post-commit
    so the Celery worker never picks up an uncommitted row).

No case was found where an external side effect (the ZATCA Celery
enqueue) happens *before* commit — that ordering is already right.

---

## Lock Ordering / Deadlock Analysis

Only two lock targets are proposed per operation at most (a document row
and, where relevant, one or more `stock_quant` rows) — the deadlock
surface is small, but a consistent order still matters for multi-line
documents:

1. **Idempotency row** (if applicable) — acquired first; it's the
   outermost guard.
2. **Document row** (`sales_order`, `purchase_order_line`, etc.) — acquired
   next.
3. **`stock_quant` rows**, if multiple lines touch multiple products —
   acquired **in a stable, deterministic order** (sort by `product_id`
   then `location_id` before locking any of them) so two transactions
   touching an overlapping set of products always request locks in the
   same relative order, preventing a circular wait.

No operation in this system needs to lock `stock_quant` rows across
*different* documents' unrelated products in the same transaction, so
cross-document deadlock risk is low — but the sort-before-lock rule
should still be followed for any multi-line document as a matter of
discipline, not because a concrete deadlock scenario was found today.

---

## Database Constraints — inventory (verified against `pg_constraint` directly)

| Table | Existing protection | Gap |
|---|---|---|
| `quotation`, `sales_order`, `sales_invoice`, `purchase_order`, `vendor_bill` | `UNIQUE(company_id, number)` | None — already closes the duplicate-number case |
| `goods_receipt` | *(none)* | **Missing `UNIQUE(company_id, number)`** — add in 16C |
| `stock_quant` | `UNIQUE(product_id, location_id)` | Prevents duplicate quant rows; does **not** prevent the lost-update race on `qty_on_hand` — that needs the row lock above, not a constraint |
| `stock_layer` | `CHECK(qty_remaining >= 0)` | Real backstop for individual layers; doesn't prevent the lost-update race between concurrent partial consumptions |
| `journal_entry`, `sales_invoice`, `zatca_submission`, `purchase_order`, `goods_receipt`, `vendor_bill` | Status-enum `CHECK` constraints | Validity checks only, not concurrency protections — correctly out of scope here |

**Proposed new constraint** (16C): `UNIQUE(company_id, number)` on
`goods_receipt`, matching its five siblings — purely additive, same
migration shape already used and proven safe in Phase 16A.

**Document numbering — sequence recommendation**: raw Postgres
`SEQUENCE` objects are global, not naturally per-company, and don't reset
per company the way `count(*)+1` does today (a fresh company must not
jump straight to a high number just because other companies have many
documents) — so a bare `CREATE SEQUENCE` per document type is not a good
fit here. The recommended replacement (16C) is a small
`document_number_counter` table keyed by `(company_id, document_type)`
with a single atomic statement:

```sql
UPDATE document_number_counter
SET last_number = last_number + 1
WHERE company_id = :company_id AND document_type = :doc_type
RETURNING last_number;
```

This is race-free without any explicit lock, because a single `UPDATE`
statement is itself atomic in Postgres — the row-level lock it implicitly
takes is held only for the duration of that one statement, and gaps from
rolled-back transactions are the normal, acceptable behavior for document
numbering (only *duplicates* are unacceptable). This is a schema/logic
change, so it belongs in 16C's implementation, not this design phase.

---

## Proposed API Behavior

- Idempotency-protected endpoints accept an optional `Idempotency-Key`
  header. If omitted, the endpoint behaves exactly as it does today (no
  behavior change for existing/non-conforming clients) — **the header is
  opt-in, not required**, so this is backward compatible with the
  frontend as it exists right now (which sends no such header).
- `409 Conflict` (RFC 7807 shape, matching this API's existing error
  format) for a reused key with a mismatched request.
- The stored, replayed response for a genuine duplicate is returned with
  its **original** HTTP status code (e.g., a replayed invoice-issuance
  returns `201`, not `200`) — the client sees the same result it would
  have seen the first time.

---

## Concurrent Test Plan

All tests must exercise genuine concurrency against the real dockerized
Postgres (matching this suite's existing pattern of never mocking the
database) — using `asyncio.gather()` to fire multiple requests through
the same `httpx.AsyncClient`/`ASGITransport` truly concurrently, not
sequentially with an illusion of concurrency.

| Test | Setup | Expected |
|---|---|---|
| Duplicate request, same `Idempotency-Key` | Two identical `POST .../invoice` calls, same key, fired via `asyncio.gather` | Exactly one `SalesInvoice`/journal entry/ZATCA submission row created; both HTTP responses show the same invoice ID and status code |
| Same key, different payload | Two `POST` calls, same key, different body (e.g., different order ID) | Second call gets `409`; only one business operation occurred |
| Concurrent stock issue | Product with `qty_on_hand = 10`; two concurrent `issue_stock` calls for 8 and 7 | Exactly one succeeds; the other fails with `InsufficientStockError` (422) — final `qty_on_hand` is `2`, never `3` and never negative |
| Concurrent document creation (no idempotency key) | Two concurrent `POST /purchasing/orders` for the same company | No duplicate `number` — losing request gets a clean `409` (translated from the `IntegrityError`, a fix needed alongside this work) rather than a raw `500` |
| Concurrent posting | Two concurrent `POST /journal-entries/{id}:post` for the same entry | Exactly one succeeds; the other gets `409` (`PostedEntryImmutableError`), not a silent double-post |
| Retry after timeout | Issue an invoice, confirm success, then re-issue an *identical* request (same key) as if simulating a client that never saw the first response | Original invoice ID and response returned; no second invoice, journal entry, or ZATCA submission created |

**Isolation level**: default READ COMMITTED — deliberately not raised to
`SERIALIZABLE`, since the row-level `FOR UPDATE` locks are the intended
mechanism, and `SERIALIZABLE` would introduce a new class of
serialization-failure retries this codebase doesn't currently handle
anywhere.

**Synchronization mechanism**: `asyncio.gather()` on coroutines that each
open their own `httpx.AsyncClient` request against the shared
`ASGITransport` app — this genuinely exercises two separate DB sessions
concurrently, since each request gets its own `AsyncSession` via
`get_db()`, matching production request handling exactly.

**Concurrent workers**: 2 per test (matching every scenario in this
task — the goal is proving pairwise races are closed, not load-testing
throughput, which is a separate, later Phase 16 item).

---

## Migration Requirements (for 16C, not this phase)

1. New `idempotency_key` table + RLS policy (additive).
2. New `UNIQUE(company_id, number)` on `goods_receipt` (additive — same
   proven-safe shape as every Phase 16A migration; no backfill needed
   since it's a constraint, not a new column).
3. New `document_number_counter` table, seeded from each existing
   numbered table's current `count(*)` per company at migration time
   (additive; requires a one-time backfill read, not a destructive
   change).

No destructive operation is proposed anywhere in this design.

---

## Performance Considerations

- **`stock_quant` `FOR UPDATE`**: locks exactly one row, for the duration
  of one short transaction (typically under 50ms in this system's
  existing test timings). Contention is expected to be low in normal
  operation (two people rarely touch the exact same product+location in
  the same instant) and the lock exists precisely to make that rare case
  correct rather than silently wrong — this is the right trade, not a
  performance risk at this system's target scale (50 companies / 200
  concurrent users, per the existing NFR).
- **`purchase_order_line` `FOR UPDATE`**: same reasoning, even lower
  contention (receiving/billing the same PO line simultaneously is rarer
  than touching the same stock item).
- **Idempotency row `FOR UPDATE`**: contention only occurs when a client
  genuinely double-fires the same request — by definition rare and, when
  it does happen, the *desired* behavior is for the second request to
  wait briefly rather than race.
- **No `FOR UPDATE` added to any read-only query** — confirmed nothing in
  this proposal touches `GET` endpoints or report/list queries.
- **No table-level locks proposed anywhere.**

---

## Risks

- **Deadlock risk**: low, given the small number of lock targets per
  operation and the documented lock-ordering rule — but this should be
  re-verified with real concurrent tests (§Concurrent Test Plan) before
  considering 16C done, not just assumed safe from this analysis alone.
- **Backward compatibility**: the `Idempotency-Key` header is opt-in;
  existing frontend code that never sends it continues to work exactly as
  today — but finding #1 remains open for *any* client that doesn't
  adopt the header, so the frontend should be updated to send it on the
  MUST-HAVE endpoints as a follow-up once 16C ships the backend piece.
- **`order.status` transition value**: choosing what the new status
  should be (`"invoiced"` vs. reusing `"done"`) is a small but real
  design decision deferred to 16C implementation — it interacts with
  whatever the frontend currently checks for "can this order still be
  edited/invoiced," which should be reviewed before picking the value.
- **Idempotency table growth**: unbounded without the cleanup job
  mentioned in §Proposed Idempotency Architecture; that job itself is
  out of scope for 16C and should be tracked as a near-term follow-up,
  not silently forgotten.

---

## Implementation Order (recommended for 16C)

1. **Fix `order.status` after invoice issuance** — the single highest-
   value, lowest-risk change in this entire document; closes the
   critical finding with a one-line fix (plus the equivalent check on the
   credit-note path) before any new infrastructure is built.
2. **Add the missing `goods_receipt` unique constraint** — trivial,
   additive, closes a confirmed gap.
3. **Add `SELECT ... FOR UPDATE` locking** to `stock_quant`/`stock_layer`
   operations and `purchase_order_line` quantity updates.
4. **Build the `idempotency_key` table + dependency/middleware** and wire
   it into the MUST-HAVE endpoints.
5. **Replace `count(*)+1` numbering** with the atomic
   `document_number_counter` pattern.
6. **Wire up the SHOULD-HAVE endpoints** with the same idempotency
   mechanism now that it exists.
7. **Write the concurrent test suite** from §Concurrent Test Plan against
   the real implementation, not before it exists.
8. **Translate remaining raw `IntegrityError`s** (document-number
   collisions, `Company.vat_number`) into clean `409` responses — a
   pre-existing gap surfaced by this audit, small enough to fold in here
   rather than opening a separate phase for it.

This order deliberately fixes the guaranteed, deterministic bug (#1)
before building any new locking or idempotency infrastructure — the
highest-value fix requires no new architecture at all.
