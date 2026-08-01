# Phase 13 — Testing

Status as of this phase: backend integration test suite green (43/43), full
manual browser verification of every module's UI, clean frontend build/lint/
typecheck. Automated frontend unit/E2E tests are **not** in place yet — see
"Known gaps" below.

## 1. Backend integration testing

**Approach**: `pytest` + `httpx.AsyncClient` (`ASGITransport`, `raise_app_exceptions=False`)
against the real dockerized Postgres — no mocking of the database or ORM.
Each test bootstraps its own fresh tenant/company/admin via
`POST /identity/bootstrap`, so tests are fully isolated from each other
(`tests/conftest.py`'s `unique_email()`/`unique_vat()` helpers guarantee no
collisions) and exercise the actual RLS policies, not a bypassed test mode.

**Suite composition** — one file per milestone, `tests/test_<module>_smoke.py`:

| File | Tests | Covers |
|---|---|---|
| `test_identity_m0_smoke.py` | 5 | bootstrap, login, 2FA, RBAC, RLS tenant isolation |
| `test_accounting_m1_smoke.py` | 11 | CoA seeding, journal entry lifecycle, trial balance, permission checks, cross-company isolation |
| `test_sales_zatca_m2_smoke.py` | 7 | quotation→order→invoice→credit-note, ZATCA hash chain/QR |
| `test_inventory_m3_smoke.py` | 9 | stock receive/transfer, FIFO/average valuation, cycle counts, insufficient-stock blocks |
| `test_purchasing_m4_smoke.py` | 8 | PO→receipt→bill→3-way-match→approve, mismatch detection, cross-company isolation |
| `test_reporting_m5_smoke.py` | 3 | dashboard KPIs, CSV export |

**Run it:**
```bash
docker compose -f infra/docker-compose.yml exec api pytest -q
```

### What this session added

Milestones M0–M5 shipped with 36 tests. This phase added 7 more, closing a
real gap: the list/detail endpoints added alongside the new frontend module
UIs (`GET /journal-entries[+/{id}]`, `GET /purchasing/orders`,
`GET /purchasing/vendor-bills`, `GET /inventory/stock/moves`) had zero
coverage before now:

- `test_list_and_get_journal_entry`, `test_get_journal_entry_not_found`,
  `test_journal_entry_not_visible_across_companies`
- `test_list_purchase_orders_and_vendor_bills`,
  `test_purchase_orders_not_visible_across_companies`
- `test_list_stock_moves`
- `test_create_account_with_unknown_type_code_rejected`

The cross-company tests matter more than they look: they're the only tests
in the suite that assert a *second* tenant's admin gets a 404 (not a 500 or
an empty-but-200), which is the actual behavior RLS is supposed to guarantee
for the new detail-by-id endpoints.

### Coverage vs. NFR-MAINT-003

NFR-MAINT-003 (docs/03) targets ≥80% line coverage on domain/application
layers. Actual, measured via `pytest --cov=src/modules --cov-report=term-missing`:

| Layer | Range across modules | Notes |
|---|---|---|
| `domain/` (entities, valuation strategies) | 80–100% | Meets target everywhere it's measured; Sales has no separate `domain/entities.py` (rules live inline in `application/services.py`) |
| `infrastructure/repositories.py` | 55–74% | Below target — largely single-purpose query methods exercised by only one or two smoke tests each |
| `application/services.py` | 34–86% | **Below target for Sales (35%) and Purchasing (34%)** — the smoke tests exercise the primary happy path and a few rejection branches per service, but not every combination (e.g. Sales' order cancellation, ZATCA reporting-mode submission as opposed to clearance, several FIFO/average edge cases) |
| `api/routes.py` | 48–61% | Below target — expected, since routes are thin wrappers already exercised transitively through the service-layer calls above; not a business-logic risk in the same way |
| **Overall (`src/modules/`)** | **74%** | |

**Honest assessment**: the *primary* business flows (the ones a user can
actually trigger from the UI) are tested end-to-end, and the isolation/
security-critical paths (RLS, permissions) are covered. The gap is in
*secondary* branches — less common error paths and alternate valuation/
tax scenarios — concentrated in Sales and Purchasing's application layer.
Closing it fully to 80% would need on the order of 20–30 more targeted
unit/integration tests per module and is a good candidate for a follow-up
session rather than folding into this one.

## 2. Frontend verification

No automated test framework is installed yet (no Jest/Vitest/Playwright in
`package.json`). What *is* in place and passing clean:

- `npx tsc --noEmit` — zero type errors (this phase fixed 12 real ones: Base
  UI's `Select.onValueChange` can be called with `null`, which several pages
  passed straight into `useState<string>` setters without a fallback)
- `npx eslint .` — zero errors (this phase fixed 2 pre-existing
  `react-hooks/set-state-in-effect` findings in `I18nProvider`/`ThemeProvider`
  — both are deliberately effect-based to avoid an SSR/hydration mismatch
  from reading `localStorage` during the initial render, so they're silenced
  with an explanatory comment rather than restructured)
- `npx next build` — production build succeeds, all 17 routes compile
  (9 static, 4 dynamic `[id]` routes)

**Manual browser verification** (Claude Browser MCP, live against the running
dev server + dockerized backend) covered the full user-facing surface for
every module in this release:

- **Auth**: bootstrap → login → dashboard, locale toggle (AR↔EN, `dir`
  flip), dark-mode toggle
- **Sales**: quotation create → confirm to order → issue invoice (verified
  the ZATCA QR renders real encoded data, not a placeholder — 30KB+ SVG path
  for a 49×49 module grid) → credit note
- **Accounting**: chart-of-accounts create, multi-line journal entry create
  → post → trial balance report reflecting the posted entry
- **Inventory**: warehouse create, stock receive, stock moves ledger
- **Purchasing**: PO create → confirm → goods receipt → vendor bill → 3-way
  match approval, cross-checked against the Dashboard's Purchases/Payables
  KPIs updating correctly (Reporting module's cross-module read confirmed
  live, not just in isolation)

### A real bug found during this pass

Base UI's `Tabs.Panel` (`@base-ui/react` v1.6) does not reliably hide
inactive panels once a second tab is switched to — its internal
`data-index` tracking never resolves past `-1` for a panel mounted after
the first render, so neither the `hidden` DOM attribute nor `data-hidden`
gets set, and both panels render their content simultaneously. Confirmed via
direct DOM inspection, not a testing-tool artifact. Fixed in all three
affected pages (`accounting`, `inventory`, `purchasing`) by tracking the
active tab in local state and gating each panel's children on it, rather
than relying on the library's built-in visibility behavior.

## 3. Known gaps

- **No automated frontend tests.** Recommend Vitest + React Testing Library
  for component-level tests and Playwright for the E2E flows this session
  verified manually, as a follow-up.
- **Sales/Purchasing application-layer coverage below the 80% NFR target**
  (see table above).
- **ZATCA Cryptographic Stamp and live gateway calls remain simulated**
  (documented already in the ZATCA module's own docstrings from Phase 11) —
  not a testing gap so much as a scope boundary of the nucleus.
- **Load/concurrency testing** (NFR-SCALE-003: 50 companies / 200 concurrent
  users) has not been attempted — deferred to Phase 14 (Deployment), where
  it belongs alongside actual infrastructure sizing.
