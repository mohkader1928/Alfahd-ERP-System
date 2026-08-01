# Phase 9 — Folder Structure

**Status:** Draft for approval | **Version:** 0.1
**Builds on:** [08-system-architecture.md](08-system-architecture.md)

This translates the module map and layering from Phase 8 into an actual repository layout. The rule that governs every decision below: **a new future module (CRM, POS, HR...) must be addable as a new folder under `modules/`, touching zero lines in any existing module** (NFR-MAINT-006).

---

## 1. Repository Layout (Top Level)

```
erp-system/
├── backend/                 # FastAPI application
├── frontend/                # Next.js application
├── docs/                    # This documentation (Phases 1-15)
├── infra/                   # Docker, deployment configs (Phase 14)
├── .github/workflows/       # CI pipelines (Phase 14)
└── README.md
```

---

## 2. Backend (`backend/`)

```
backend/
├── src/
│   ├── modules/
│   │   ├── identity/                 # M0 — Company, Branch, User, RBAC, Audit
│   │   │   ├── domain/
│   │   │   │   ├── entities.py       # Company, Branch, User, Role, Permission
│   │   │   │   ├── value_objects.py  # VatNumber, Email, etc.
│   │   │   │   ├── events.py         # UserLoggedIn, PermissionChanged
│   │   │   │   └── repositories.py   # abstract interfaces (Protocol/ABC)
│   │   │   ├── application/
│   │   │   │   ├── commands/         # CreateCompany, AssignRole, ...
│   │   │   │   ├── queries/          # GetUserPermissions, ListAuditLog, ...
│   │   │   │   └── services.py       # orchestration, calls repos + domain
│   │   │   ├── infrastructure/
│   │   │   │   ├── models.py         # SQLAlchemy ORM models
│   │   │   │   └── repositories.py   # concrete repo implementations
│   │   │   ├── api/
│   │   │   │   ├── routes.py         # FastAPI router for this module
│   │   │   │   └── schemas.py        # Pydantic request/response models
│   │   │   └── tests/
│   │   │       ├── unit/             # domain + application, no DB
│   │   │       └── integration/      # repository + API, real test DB
│   │   │
│   │   ├── accounting/                # M1 — CoA, Journals, Tax Engine
│   │   │   ├── domain/                # Account, JournalEntry, TaxEngine (pure logic)
│   │   │   ├── application/
│   │   │   ├── infrastructure/
│   │   │   ├── api/
│   │   │   └── tests/
│   │   │
│   │   ├── sales/                     # M2 — Quotation → Invoice
│   │   │   ├── domain/
│   │   │   ├── application/
│   │   │   ├── infrastructure/
│   │   │   ├── api/
│   │   │   └── tests/
│   │   │
│   │   ├── zatca/                     # M2 — isolated ZATCA adapter module
│   │   │   ├── domain/                # SubmissionResult, HashChain value objects
│   │   │   ├── application/           # ClearInvoice, ReportInvoice use cases
│   │   │   ├── infrastructure/
│   │   │   │   ├── gateways/
│   │   │   │   │   ├── sandbox_gateway.py
│   │   │   │   │   ├── production_gateway.py
│   │   │   │   │   └── base.py        # IZatcaGateway interface
│   │   │   │   ├── xml_builder.py     # UBL 2.1 XML generation
│   │   │   │   ├── signing.py         # Cryptographic Stamp / CSID handling
│   │   │   │   └── qr_encoder.py      # TLV/Base64 QR generation
│   │   │   ├── api/                   # internal only — no public HTTP routes;
│   │   │   │                          # invoked in-process by sales/, per Phase 8 §3
│   │   │   └── tests/
│   │   │
│   │   ├── inventory/                 # M3 — Warehouses, Stock, Valuation
│   │   │   ├── domain/
│   │   │   │   └── valuation/
│   │   │   │       ├── strategy.py    # IValuationStrategy
│   │   │   │       ├── fifo.py
│   │   │   │       └── average.py
│   │   │   ├── application/
│   │   │   ├── infrastructure/
│   │   │   ├── api/
│   │   │   └── tests/
│   │   │
│   │   ├── purchasing/                # M4 — PO → Receipt → Bill
│   │   │   ├── domain/
│   │   │   ├── application/
│   │   │   ├── infrastructure/
│   │   │   ├── api/
│   │   │   └── tests/
│   │   │
│   │   └── reporting/                 # M5 — cross-module read-only reports
│   │       ├── application/           # read-only query services only
│   │       ├── infrastructure/
│   │       │   └── exporters/         # pdf_exporter.py, excel_exporter.py
│   │       ├── api/
│   │       └── tests/
│   │
│   ├── shared/                        # cross-cutting, imported by every module
│   │   ├── domain/
│   │   │   └── base_entity.py         # common envelope (Phase 7 §1.1) as a mixin
│   │   ├── infrastructure/
│   │   │   ├── db/
│   │   │   │   ├── session.py         # SQLAlchemy session factory
│   │   │   │   ├── base_repository.py # generic CRUD + RLS tenant-context setter
│   │   │   │   └── unit_of_work.py
│   │   │   ├── cache/redis_client.py
│   │   │   ├── storage/               # local filesystem vs S3 adapter
│   │   │   └── messaging/
│   │   │       ├── event_bus.py       # in-process domain event dispatcher
│   │   │       └── celery_app.py
│   │   ├── security/
│   │   │   ├── jwt.py
│   │   │   ├── rbac.py                # permission-check decorators/dependencies
│   │   │   └── password_policy.py
│   │   ├── i18n/
│   │   │   └── translations/{ar,en}.json
│   │   └── config/settings.py         # env-based configuration (NFR-PORT-002)
│   │
│   ├── api/
│   │   ├── main.py                    # FastAPI app; loops over modules' register() fn
│   │   └── middleware/
│   │       ├── auth_middleware.py
│   │       ├── tenant_context_middleware.py   # sets RLS session var per request
│   │       └── error_handler.py
│   │
│   └── workers/
│       ├── celery_app.py
│       └── tasks/
│           ├── zatca_tasks.py         # clearance/reporting/retry-sweep jobs
│           └── report_tasks.py        # large export jobs
│
├── migrations/                        # Alembic, one subfolder per module namespace
│   ├── identity/
│   ├── accounting/
│   ├── sales/
│   ├── zatca/
│   ├── inventory/
│   └── purchasing/
│
├── tests/
│   └── conftest.py                    # shared fixtures (test DB, test client)
│
├── pyproject.toml
├── Dockerfile
└── .env.example
```

### 2.1 Module Registration Pattern (enforces "add without modifying")

Each module exposes a single entry point:

```python
# modules/sales/__init__.py
def register(app: FastAPI, event_bus: EventBus) -> None:
    app.include_router(sales_routes.router, prefix="/api/v1/sales")
    event_bus.subscribe(InvoiceCleared, notify_customer_handler)
```

`api/main.py` only does:

```python
for module in ENABLED_MODULES:  # config-driven list
    module.register(app, event_bus)
```

Adding a future module (e.g. `modules/crm/`) means writing its `register()` and adding one line to `ENABLED_MODULES` — no existing module file changes.

---

## 3. Frontend (`frontend/`)

```
frontend/
├── app/                                # Next.js App Router — routing only, thin
│   ├── (auth)/
│   │   └── login/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx                  # shell: sidebar, topbar, notifications
│   │   ├── sales/
│   │   │   ├── quotations/page.tsx
│   │   │   ├── orders/page.tsx
│   │   │   └── invoices/page.tsx
│   │   ├── accounting/
│   │   │   ├── journal-entries/page.tsx
│   │   │   └── reports/trial-balance/page.tsx
│   │   ├── inventory/
│   │   │   ├── warehouses/page.tsx
│   │   │   └── transfers/page.tsx
│   │   ├── purchasing/
│   │   │   ├── orders/page.tsx
│   │   │   └── bills/page.tsx
│   │   └── admin/
│   │       ├── companies/page.tsx
│   │       ├── users/page.tsx
│   │       └── roles/page.tsx
│   └── layout.tsx                      # root layout: locale, theme provider
│
├── features/                           # mirrors backend modules/ 1:1
│   ├── identity/
│   │   ├── api/                        # typed client, generated from OpenAPI (Phase 10)
│   │   ├── components/
│   │   ├── hooks/                      # React Query hooks
│   │   └── store/                      # Zustand slice (auth state)
│   ├── accounting/
│   │   ├── api/
│   │   ├── components/
│   │   └── hooks/
│   ├── sales/
│   │   ├── api/
│   │   ├── components/
│   │   │   ├── QuotationForm.tsx
│   │   │   ├── SalesOrderKanban.tsx
│   │   │   └── InvoicePreview.tsx      # includes QR code rendering
│   │   └── hooks/
│   ├── inventory/
│   ├── purchasing/
│   └── reporting/
│       └── components/DashboardWidgets/
│
├── components/                         # shared, feature-agnostic UI (shadcn-based)
│   ├── ui/                             # Button, Table, Dialog, SmartButton, KanbanBoard...
│   ├── layout/                         # Sidebar, Topbar, GlobalSearch
│   └── forms/                          # shared form primitives (React Hook Form + Zod)
│
├── lib/
│   ├── api-client.ts                   # base fetch wrapper (auth header, error handling)
│   ├── react-query-client.ts
│   ├── i18n/
│   │   ├── ar.json
│   │   ├── en.json
│   │   └── config.ts
│   └── calendar/hijri-gregorian.ts
│
├── stores/
│   ├── auth-store.ts                   # Zustand: current user, company/branch context
│   └── ui-store.ts                     # locale, theme, sidebar collapsed state
│
├── middleware.ts                       # route guard (auth check), locale detection
├── next.config.js
├── tailwind.config.ts
└── package.json
```

### 3.1 Feature Module Isolation Rule

A component inside `features/sales/` may import from `components/` (shared) and `lib/` (shared), but **never** from `features/accounting/` or any other feature directly. If Sales needs accounting data (e.g., a payment status), it goes through that feature's public `api/` client hitting the backend's Sales module API — the same module-boundary discipline as the backend, applied to the frontend.

---

## 4. Why This Structure Satisfies Phase 8's Constraints

| Phase 8 requirement | How the structure satisfies it |
|----------------------|----------------------------------|
| Dependency rule (domain has no infra/presentation dependency) | `domain/` files never import from `infrastructure/` or `api/` — enforced by import-linter rule in CI (Phase 14) |
| Module isolation (Section 1.1) | One folder per bounded context, own `tests/`, own migration namespace, communication only via `application/services.py` public methods and `shared/infrastructure/messaging/event_bus.py` |
| ZATCA as a leaf/adapter module | `modules/zatca/` has no `api/routes.py` registered publicly — it's a library used by `modules/sales/`, matching the "only Sales may call ZATCA" rule |
| Add-without-modifying for future modules | Module registration pattern (Section 2.1) |

---

## 5. General Acceptance Criteria

- [ ] Project owner (or technical delegate) approves this folder structure as the actual repository layout to scaffold in Phase 11/12.
- [ ] Any deviation discovered during implementation is reflected back into this document, not silently drifted from.

---

*End of Phase 9. Proceeding to Phase 10: API Design.*
