# Saudi ERP System — Core Nucleus

A modular-monolith ERP built for the Saudi market, covering Foundation
(multi-tenant/RBAC/audit), Accounting, Sales with ZATCA e-invoicing,
Inventory, Purchasing, and basic Reporting. Built following a 15-phase
methodology from business analysis through deployment — every phase's
design record lives in [`docs/`](docs/).

**Status**: functional nucleus, not production-hardened. See
[Scope and limitations](#scope-and-limitations) before relying on this for
real financial/tax data.

## Stack

| | |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16 (Row-Level Security for multi-tenancy), Redis, Celery |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui on Base UI, TanStack Query, Zustand |
| Infra | Docker Compose (dev + production topologies) |

## Quickstart (local dev)

```bash
cd infra

# 1. Start Postgres + Redis first
docker compose up -d postgres redis

# 2. Bootstrap DB roles + run migrations (first time / after pulling new
#    ones) — a dedicated one-off service, not part of `up`. See
#    docs/17c-rls-runtime-role-hardening.md for why this is a separate
#    step from #3: the API/worker connect with a restricted runtime role
#    that can't run migrations itself.
docker compose --profile tools run --rm migrate

# 3. Start the API + worker
docker compose up -d api worker

# 4. Start the frontend
cd ../frontend
npm install
npm run dev
```

Open http://localhost:3000, click "Need to set up a new company?" to
bootstrap the first tenant, company, and admin user. The backend's
interactive API docs are at http://localhost:8000/docs (auto-generated
OpenAPI — satisfies NFR-MAINT-004: 100% endpoint coverage, generated from
code, not hand-maintained).

See [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md) for module-specific commands
(tests, linting, migrations).

## Repository layout

```
erp-system/
├── backend/      # FastAPI app — modules/{identity,accounting,sales,zatca,
│                 #   inventory,purchasing,reporting}, each with its own
│                 #   domain/application/infrastructure/api layers
├── frontend/     # Next.js app — app/(auth), app/(dashboard)/{module}/...
├── docs/         # Phases 1-14 design record (see below)
└── infra/        # Docker Compose (dev + prod), nginx reverse proxy config
```

Full rationale for this layout — including the rule that a future module
(CRM, POS, HR, ...) must be addable as a new folder under `modules/`
without touching existing ones — is in
[`docs/09-folder-structure.md`](docs/09-folder-structure.md).

## Documentation

Each phase's design record, in order:

| Phase | Doc |
|---|---|
| 1. Business Analysis | [01-business-analysis.md](docs/01-business-analysis.md) |
| 2. Functional Requirements | [02-functional-requirements.md](docs/02-functional-requirements.md) |
| 3. Non-Functional Requirements | [03-non-functional-requirements.md](docs/03-non-functional-requirements.md) |
| 4. Use Cases | [04-use-cases.md](docs/04-use-cases.md) |
| 5. Business Flow | [05-business-flow.md](docs/05-business-flow.md) |
| 6. ER Diagram | [06-er-diagram.md](docs/06-er-diagram.md) |
| 7. Database Design | [07-database-design.md](docs/07-database-design.md) |
| 8. System Architecture | [08-system-architecture.md](docs/08-system-architecture.md) |
| 9. Folder Structure | [09-folder-structure.md](docs/09-folder-structure.md) |
| 10. API Design | [10-api-design.md](docs/10-api-design.md) |
| 11-12. Backend/Frontend Development | (code — no separate doc; see module READMEs) |
| 13. Testing | [11-testing.md](docs/11-testing.md) |
| 14. Deployment | [14-deployment.md](docs/14-deployment.md) |

## Scope and limitations

This is a **nucleus**, not the full product: only the six modules listed
above are built. CRM, POS, Manufacturing, Construction, HR, and the rest of
a full ERP suite are deferred to a backlog, deliberately, per the
"core nucleus first" scope decision at the start of this project.

Within the built scope, be aware of:

- **ZATCA e-invoicing is not production-certified.** UUID/ICV sequencing,
  SHA-256 hash chaining, and TLV/Base64 QR encoding are real and correct;
  the Cryptographic Stamp is an HMAC placeholder (needs a real CSID
  certificate from ZATCA), and the gateway calls hit a sandbox simulator,
  not ZATCA's actual Clearance/Reporting API. Do not use this for real
  Saudi tax filings without completing ZATCA onboarding and swapping in a
  real production gateway (the `IZatcaGateway` interface exists precisely
  so this is a config/DI change, not a rewrite — see
  [08-system-architecture.md §"Path to Future Microservice Extraction"](docs/08-system-architecture.md)).
- **Automated test coverage on Sales/Purchasing's application layer is
  below the project's own 80% NFR target** (34-35% measured) — the primary
  flows are tested, secondary branches (alternate valuation scenarios,
  order cancellation, ZATCA reporting-mode vs. clearance-mode) are not yet.
  Full detail in [docs/11-testing.md](docs/11-testing.md).
- **No automated frontend tests** — the UI was verified manually via live
  browser testing (documented in the testing doc) rather than an automated
  suite.
- **Deployment covers containerized topology, not cloud provisioning** — no
  TLS termination, no CI/CD pipeline, no cloud-specific infra. See
  [docs/14-deployment.md §7](docs/14-deployment.md) for the full deferred list.

None of these are hidden — each is called out in the relevant phase doc
with what would be needed to close the gap.
