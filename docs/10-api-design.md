# Phase 10 — API Design

**Status:** Draft for approval | **Version:** 0.1
**Builds on:** [09-folder-structure.md](09-folder-structure.md)

The nucleus exposes a **REST API only** (GraphQL explicitly deferred per Phase 1 §6). Every endpoint below maps back to an FR from Phase 2 — no endpoint is invented that isn't traceable to a requirement.

---

## 1. General Conventions

- **Base path:** `/api/v1/<module>/<resource>` — module prefix matches the backend module name (`sales`, `accounting`, `inventory`, `purchasing`, `identity`, `reporting`). `zatca` has no public prefix (internal-only, per Phase 9 §2).
- **Versioning:** URL-path versioned (`/v1/`). A breaking change ships as `/v2/` alongside `/v1/` until deprecation, never an in-place breaking change.
- **Verbs:** standard REST — `GET` (read), `POST` (create / action), `PATCH` (partial update), `DELETE` (soft delete only, per FR-CORE-021).
- **Actions that aren't pure CRUD** (confirm a sales order, post a journal entry, clear an invoice) are modeled as `POST /resource/{id}:action`, e.g. `POST /sales/orders/{id}:confirm` — avoids overloading `PATCH` with business-meaning state transitions.

---

## 2. Authentication & Context

```
Authorization: Bearer <JWT access token>
```

JWT claims carry: `sub` (user id), `tenant_id`, `authorized_companies` (list of company/branch pairs), `exp`. The active company/branch for a request is selected explicitly:

```
X-Company-Id: <uuid>
X-Branch-Id: <uuid>        (optional; omitted = company-wide where valid)
```

The API rejects any request where `X-Company-Id` isn't in the token's `authorized_companies` (FR-CORE-003) — this is where the `tenant_context_middleware` (Phase 9 §2) sets the PostgreSQL RLS session variable.

- `POST /api/v1/identity/auth/login` → `{access_token, refresh_token}` (+ TOTP challenge step if 2FA enabled)
- `POST /api/v1/identity/auth/refresh`
- `POST /api/v1/identity/auth/logout`

---

## 3. Standard Response Envelope

**Single resource:**
```json
{ "data": { "id": "...", "...": "..." } }
```

**List (paginated):**
```json
{
  "data": [ { "...": "..." } ],
  "meta": { "page": 1, "page_size": 50, "total_count": 214, "total_pages": 5 }
}
```

**List query parameters (FR-CORE-054):**
`?page=1&page_size=50&sort=-created_at&filter[status]=confirmed&filter[partner_id]=<uuid>&group_by=partner_id`

---

## 4. Error Format (RFC 7807 Problem Details)

```json
{
  "type": "urn:erp:error:validation-failed",
  "title": "Validation Failed",
  "status": 422,
  "detail": "total debit does not equal total credit",
  "instance": "/api/v1/accounting/journal-entries",
  "errors": [
    { "field": "lines[2].credit", "message": "must be >= 0" }
  ]
}
```

| HTTP Status | Meaning |
|-------------|---------|
| 400 | Malformed request |
| 401 | Missing/invalid JWT |
| 403 | Authenticated but not authorized (RBAC/Record Rule/company scope) |
| 404 | Resource not found or soft-deleted |
| 409 | Optimistic lock conflict (`version` mismatch) or business-rule conflict (e.g. unbalanced entry) |
| 422 | Validation error |
| 429 | Rate limited |
| 502 | Upstream failure (e.g. ZATCA unreachable — see idempotency note below) |

---

## 5. Idempotency for Financial Mutations

Any endpoint that creates a financially-significant, externally-numbered document (invoices, journal postings) accepts an optional `Idempotency-Key` header. If a request with the same key + same company was already processed, the original result is returned instead of creating a duplicate — critical for ZATCA submission retries (FR-ZATCA-009, NFR-AVAIL-003) where a client timeout must never produce two invoice numbers for one sale.

```
POST /api/v1/sales/invoices
Idempotency-Key: 8f14e45f-...
```

---

## 6. Endpoint Catalog by Module

### 6.1 Identity (`/api/v1/identity`) — FR-CORE-*

| Method | Path | Purpose | FR |
|--------|------|---------|-----|
| POST | `/auth/login` | Login (+2FA challenge) | FR-CORE-010/011 |
| GET | `/companies` | List companies user can access | FR-CORE-001 |
| POST | `/companies` | Create company (System Admin) | FR-CORE-040 |
| POST | `/companies/{id}/branches` | Create branch | FR-CORE-002 |
| GET | `/users` | List users | FR-CORE-041 |
| POST | `/users` | Create user | FR-CORE-041 |
| POST | `/users/{id}/roles` | Assign role | FR-CORE-014 |
| GET | `/roles/{id}/permissions` | View role's permission matrix | FR-CORE-015..017 |
| GET | `/audit-log` | Query audit trail | FR-CORE-022, FR-RPT-004 |
| GET | `/partners` | List customers/vendors | FR-CORE-042 |
| POST | `/partners` | Create partner | FR-CORE-042 |
| GET | `/products` | List products | FR-CORE-045 |
| POST | `/products` | Create product | FR-CORE-045 |
| POST | `/attachments` | Upload attachment (multipart) | FR-CORE-050 |
| GET | `/notifications` | List current user's notifications | FR-CORE-051 |
| GET | `/search?q=` | Global search | FR-CORE-053 |

### 6.2 Accounting (`/api/v1/accounting`) — FR-ACC-*

| Method | Path | Purpose | FR |
|--------|------|---------|-----|
| GET | `/chart-of-accounts` | List accounts (tree) | FR-ACC-001 |
| POST | `/journal-entries` | Create draft entry | FR-ACC-002 |
| POST | `/journal-entries/{id}:post` | Post entry (validates balance) | FR-ACC-002/003 |
| POST | `/journal-entries/{id}:reverse` | Create reversal entry | FR-ACC-004 |
| GET | `/reports/trial-balance?date_from=&date_to=&branch_id=` | Trial balance | FR-ACC-009 |
| GET | `/reports/income-statement` | P&L | FR-ACC-010 |
| GET | `/reports/balance-sheet` | Balance sheet | FR-ACC-010 |
| POST | `/fiscal-periods/{id}:close` | Close period | FR-ACC-011 |

### 6.3 Sales (`/api/v1/sales`) — FR-SAL-* / FR-ZATCA-*

| Method | Path | Purpose | FR |
|--------|------|---------|-----|
| POST | `/quotations` | Create quotation | FR-SAL-001 |
| POST | `/quotations/{id}:confirm` | Convert to Sales Order | FR-SAL-002 |
| POST | `/orders/{id}:confirm` | Confirm sales order | FR-SAL-002 |
| POST | `/deliveries/{id}:confirm` | Confirm delivery (deducts stock) | FR-SAL-003 |
| POST | `/invoices` | Issue invoice (routes to ZATCA internally) | FR-SAL-004, FR-ZATCA-001..008 |
| GET | `/invoices/{id}` | Get invoice incl. QR/status | FR-ZATCA-006 |
| POST | `/invoices/{id}:credit-note` | Issue credit note | FR-SAL-005 |
| GET | `/price-lists` | List price lists | FR-SAL-006 |

### 6.4 Inventory (`/api/v1/inventory`) — FR-INV-*

| Method | Path | Purpose | FR |
|--------|------|---------|-----|
| GET | `/warehouses` | List warehouses | FR-INV-001 |
| GET | `/stock-quants?product_id=&location_id=` | Current balances | FR-INV-002 |
| POST | `/transfers` | Create stock transfer | FR-INV-003 |
| POST | `/transfers/{id}:confirm` | Confirm transfer | FR-INV-003 |
| POST | `/cycle-counts` | Create cycle count session | FR-INV-006 |
| POST | `/cycle-counts/{id}:approve` | Approve counted discrepancies | FR-INV-006 |

### 6.5 Purchasing (`/api/v1/purchasing`) — FR-PUR-*

| Method | Path | Purpose | FR |
|--------|------|---------|-----|
| POST | `/orders` | Create purchase order | FR-PUR-001 |
| POST | `/orders/{id}:confirm` | Confirm PO (may trigger approval) | FR-PUR-001, FR-CORE-052 |
| POST | `/goods-receipts` | Record receipt | FR-PUR-002 |
| POST | `/vendor-bills` | Register vendor bill | FR-PUR-003 |
| POST | `/vendor-bills/{id}:approve` | Approve after 3-way match | FR-PUR-003 |

### 6.6 Reporting (`/api/v1/reporting`) — FR-RPT-*

| Method | Path | Purpose | FR |
|--------|------|---------|-----|
| GET | `/dashboard` | Nucleus KPI summary | FR-RPT-003 |
| GET | `/export/{module}/{resource}?format=pdf\|xlsx` | Export any listable resource | FR-RPT-001/002 |

### 6.7 Approval Engine (cross-cutting, exposed under `/identity`)

| Method | Path | Purpose | FR |
|--------|------|---------|-----|
| GET | `/identity/approvals?status=pending` | My pending approvals | FR-CORE-052 |
| POST | `/identity/approvals/{id}:approve` | Approve | FR-CORE-052 |
| POST | `/identity/approvals/{id}:reject` | Reject with comment | FR-CORE-052 |

---

## 7. OpenAPI / Documentation Plan (NFR-MAINT-004)

- FastAPI auto-generates the OpenAPI 3.1 schema from route + Pydantic schema definitions — **never hand-written**, so it cannot drift from the actual implementation.
- Served at `/api/v1/openapi.json`, interactive docs at `/api/docs` (Swagger UI) and `/api/redoc`.
- A snapshot is exported to `docs/api/openapi.snapshot.json` on every release (Phase 14 CI step) so API changes are diffable in code review.
- Frontend's typed API clients (Phase 9 §3, `features/*/api/`) are code-generated from this spec (e.g. via `openapi-typescript`), so backend/frontend contract drift becomes a build-time type error, not a runtime bug.

---

## 8. Rate Limiting (NFR-SEC-006)

Applied at the reverse-proxy/middleware layer:

| Scope | Limit |
|-------|-------|
| `/auth/login` | 5 failed attempts / 15 min per account + IP |
| All other authenticated endpoints | 300 requests / min per user (generous default; tightened per-endpoint if abuse is observed) |

Response includes standard headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After` on 429.

---

## 9. General Acceptance Criteria

- [ ] Project owner (or technical delegate) approves the endpoint catalog, response envelope, and idempotency approach for financial documents.
- [ ] No backend implementation (Phase 11) begins on an endpoint not listed here without first amending this document.

---

*End of Phase 10 — the full design chain (Phases 1–10) is now complete. Proceeding to Phase 11: Backend Development.*
