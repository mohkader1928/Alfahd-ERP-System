# Phase 3 — Non-Functional Requirements

**Status:** Draft for approval | **Version:** 0.1
**Builds on:** [01-business-analysis.md](01-business-analysis.md), [02-functional-requirements.md](02-functional-requirements.md)

---

## 1. Numbering & Priority Scheme

`NFR-<Category>-<Seq>`, same MoSCoW priority as Phase 2 (M/S/C). Each requirement includes a measurable target where applicable — a Must-priority NFR without a measurable target is not considered complete.

---

## 2. NFR-PERF — Performance

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-PERF-001 | List screen API response time (paginated, ≤50 rows) | p95 < 300ms under nominal load | M |
| NFR-PERF-002 | Document posting (invoice confirm, journal post, stock move) | p95 < 800ms including journal-entry generation | M |
| NFR-PERF-003 | ZATCA invoice generation + signing (local, excluding network round-trip to ZATCA) | p95 < 500ms | M |
| NFR-PERF-004 | Dashboard load (M5 KPIs) | p95 < 1.5s | S |
| NFR-PERF-005 | Report export (PDF/Excel, ≤5,000 rows) | < 5s, executed as a background job above that threshold | S |
| NFR-PERF-006 | Database queries use indexes on all filter/sort columns exposed in list screens; no full table scans on tables projected to exceed 100k rows | — | M |
| NFR-PERF-007 | Read-heavy master data (currencies, UoM, tax rates) is cached (Redis) with explicit invalidation on write | cache hit ratio > 90% | S |

---

## 3. NFR-SCALE — Scalability

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-SCALE-001 | The backend is stateless (session/JWT-based) so multiple instances can run behind a load balancer without sticky sessions | — | M |
| NFR-SCALE-002 | Each bounded-context module keeps its own tables/foreign keys logically isolated, so it can be extracted into a separate service later without a schema rewrite | validated at architecture review (Phase 8) | M |
| NFR-SCALE-003 | Nucleus supports at minimum 50 concurrent companies and 200 concurrent active users without performance degradation beyond NFR-PERF targets | load test at design capacity | S |
| NFR-SCALE-004 | Heavy/long-running operations (bulk import, large report export, ZATCA batch reporting) run as background jobs, not inline in the request/response cycle | — | M |

---

## 4. NFR-AVAIL — Availability & Reliability

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-AVAIL-001 | Core nucleus uptime target (production deployment) | 99.5% monthly | S |
| NFR-AVAIL-002 | Database backups | automated daily full backup + continuous WAL archiving, restorable within 4 hours (RTO), max 15 min data loss (RPO) | M |
| NFR-AVAIL-003 | ZATCA integration failure (authority endpoint down/timeout) must not block invoice creation; invoice is saved locally with a "pending submission" status and retried automatically | — | M |
| NFR-AVAIL-004 | All financially-significant operations (posting, invoicing, stock valuation) run inside a database transaction — partial writes are impossible | — | M |
| NFR-AVAIL-005 | Graceful degradation: if Redis is unavailable, the system continues to function without caching rather than failing requests | — | S |

---

## 5. NFR-SEC — Security

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-SEC-001 | All network traffic (frontend↔backend, backend↔DB, backend↔ZATCA) encrypted in transit via TLS 1.2+ | — | M |
| NFR-SEC-002 | Sensitive data at rest (passwords, tokens, ZATCA private keys/certificates) encrypted; passwords hashed with a modern algorithm (Argon2/bcrypt), never stored/logged in plaintext | — | M |
| NFR-SEC-003 | Secrets (DB credentials, JWT signing keys, ZATCA certs) loaded from a secrets manager or environment configuration, never committed to source control | — | M |
| NFR-SEC-004 | All API inputs validated and sanitized server-side (schema validation) regardless of client-side validation, to prevent injection (SQL/NoSQL/command) | — | M |
| NFR-SEC-005 | Protection against OWASP Top 10 classes: injection, broken auth, XSS, broken access control, SSRF, insecure deserialization | verified via security review before each milestone release | M |
| NFR-SEC-006 | Rate limiting on authentication endpoints to mitigate brute-force attacks | e.g. max 5 failed attempts / 15 min per account+IP | M |
| NFR-SEC-007 | Dependency vulnerability scanning integrated into CI (Phase 14) | no known critical/high CVEs at release | S |
| NFR-SEC-008 | Every state-changing API call is authorized via RBAC checks at the service layer, not only hidden in the UI | — | M |

---

## 6. NFR-MAINT — Maintainability & Code Quality

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-MAINT-001 | Backend follows Clean Architecture / DDD layering (domain, application, infrastructure, presentation) with dependencies pointing inward | verified at architecture review | M |
| NFR-MAINT-002 | Every module is independently testable (no hidden cross-module coupling except through defined interfaces) | — | M |
| NFR-MAINT-003 | Automated test coverage on domain/application layers | ≥ 80% line coverage on core business logic | S |
| NFR-MAINT-004 | Every public API endpoint documented via OpenAPI/Swagger, generated from code (not hand-maintained) | 100% endpoint coverage | M |
| NFR-MAINT-005 | Consistent code style enforced via linting/formatting tools in CI (backend: ruff/black; frontend: eslint/prettier) | CI fails on violation | S |
| NFR-MAINT-006 | No module modification required to add a new, unrelated future module (Open/Closed Principle at the module-registration level) | validated in Phase 8/9 design | M |

---

## 7. NFR-OBS — Observability

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-OBS-001 | Structured logging (JSON) for all requests, including a correlation/request ID traceable end-to-end | — | M |
| NFR-OBS-002 | All errors (5xx, unhandled exceptions) captured with stack trace and request context, without leaking sensitive data (passwords, full card numbers, etc.) into logs | — | M |
| NFR-OBS-003 | Health-check endpoint (`/health`) reporting DB, Redis, and queue connectivity | — | M |
| NFR-OBS-004 | Key business metrics exposed for monitoring (invoices created/failed, ZATCA submission success rate, job queue depth) | S |

---

## 8. NFR-COMPLY — Compliance & Legal (Saudi Context)

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-COMPLY-001 | ZATCA e-invoicing technical requirements (Phase 1 generation + Phase 2 integration) are treated as binding non-functional constraints, not just features — see FR-ZATCA-* | — | M |
| NFR-COMPLY-002 | Personal data handling complies with the Saudi Personal Data Protection Law (PDPL): data minimization, purpose limitation, and a documented basis for storing customer/employee personal data | — | M |
| NFR-COMPLY-003 | Data residency: production database hosted in a KSA region when deployed for a Saudi entity subject to data-residency obligations (deployment-time configuration, not hardcoded) | — | S |
| NFR-COMPLY-004 | Audit trail retention sufficient to satisfy ZATCA's minimum invoice/record retention period (6 years) | soft-deleted/archived, never purged before the retention window | M |

---

## 9. NFR-USE — Usability & Accessibility

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-USE-001 | Primary workflows (quotation-to-invoice, PO-to-bill) completable by a trained user without consulting external documentation | validated via usability walkthrough | S |
| NFR-USE-002 | Responsive layout functional down to tablet width (≥768px); full desktop optimization is the primary target for the nucleus | — | S |
| NFR-USE-003 | Critical user actions (delete, post, cancel) require explicit confirmation | — | M |
| NFR-USE-004 | Form validation errors are field-specific and shown inline, not as a generic failure message | — | S |

---

## 10. NFR-PORT — Portability & Deployment

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-PORT-001 | Backend and frontend are containerized (Docker) and runnable identically in cloud or on-premise environments | — | M |
| NFR-PORT-002 | All environment-specific values (DB host, secrets, ZATCA sandbox/production endpoint) are externalized to configuration, never hardcoded | — | M |
| NFR-PORT-003 | No cloud-vendor-specific service is a hard dependency of the nucleus (e.g., no direct lock-in to a proprietary managed queue); standard PostgreSQL/Redis/RabbitMQ-compatible services only | — | S |

---

## 11. Traceability to Business Objectives

| Business Objective (Phase 1) | Related NFRs |
|-------------------------------|----------------|
| BO-1 ZATCA compliance | NFR-COMPLY-001, NFR-COMPLY-004, NFR-AVAIL-003 |
| BO-2 Multi-company/branch | NFR-SCALE-002, NFR-SEC-008 |
| BO-6 Enterprise security | NFR-SEC-001..008 |
| BO-7 Architectural scalability | NFR-SCALE-001..004, NFR-MAINT-001, NFR-MAINT-006, NFR-PORT-001..003 |
| (cross-cutting) reliability of financial data | NFR-AVAIL-002, NFR-AVAIL-004 |

---

## 12. General Acceptance Criteria

- [ ] Project owner approves the NFR list and targets, or requests specific changes.
- [ ] Any Must-priority NFR without a clear, testable target is clarified before moving to the next phase.

---

*End of Phase 3. Awaiting approval to proceed to Phase 4: Use Cases.*
