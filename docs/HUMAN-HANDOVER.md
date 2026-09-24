# Alfahd ERP — Human Engineer Handover Guide

> Master handover guide for transferring technical responsibility for Alfahd ERP
> to a professional human software engineer.
>
> This document is an index and operational handover guide. It does not replace
> the architecture, development, testing, release, recovery, or current-state
> documents referenced below.
>
> Never store passwords, tokens, private keys, database credentials, or other
> secrets in this document or in the repository.

## 1. Purpose

Alfahd ERP must remain maintainable without access to Claude, ChatGPT, Codex,
private AI conversations, terminal history, or the memory of a previous engineer.

A new qualified engineer should be able to understand, operate, troubleshoot,
test, release, and safely hand over the system using:

1. the Git repository;
2. repository documentation;
3. approved credentials supplied separately;
4. verified runtime evidence;
5. the formal Owner approval process.

Repository documentation and verified runtime evidence are the source of truth.

If documentation conflicts with Production, do not guess. Verify safely,
record the discrepancy, and update the documentation through the normal
review and approval process.

## 2. Mandatory Reading Order

Before making code or Production changes, read:

1. `/AGENTS.md`
2. `docs/CURRENT_STATE.md`
3. `docs/08-system-architecture.md`
4. `docs/20-developer-guide.md`
5. `docs/11-testing.md`
6. `docs/14-deployment.md`
7. `docs/21-disaster-recovery-and-rollback.md`
8. `docs/RELEASE-RUNBOOK.md`
9. `docs/16-multi-tenancy-hardening.md`
10. `docs/17c-rls-runtime-role-hardening.md`

For frontend work also read:

- `frontend/AGENTS.md`
- `frontend/README.md`

Some historical documents may be stale. `docs/CURRENT_STATE.md` and verified
runtime evidence take precedence for current operational facts.

## 3. System Overview

Alfahd ERP is a Saudi-market ERP implemented as a modular monolith.

Primary business areas include:

- Foundation / Identity
- Multi-tenancy
- RBAC
- Audit
- Accounting
- Sales
- ZATCA integration
- Inventory
- Purchasing
- Reporting
- Payments
- Fixed Assets

Primary technology stack:

### Backend

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic
- Redis
- Celery

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS

### Infrastructure

- Ubuntu/Linux
- Docker / Docker Compose
- Nginx
- PM2
- Git / GitHub

Read `docs/08-system-architecture.md` and `docs/20-developer-guide.md` for the
actual architecture, module boundaries, RLS model, authentication, RBAC,
migrations, API conventions, audit behavior, and testing details.

## 4. Current Production Model

Do not rely on this section alone for release work. Always confirm
`docs/CURRENT_STATE.md` first.

At the last verified handover state:

- Nginx runs on the Production host.
- Next.js runs on the host under PM2.
- Frontend PM2 process is `alfahd-frontend`.
- API runs in Docker Compose.
- Celery Worker runs in Docker Compose.
- PostgreSQL runs in Docker Compose.
- Redis runs in Docker Compose.
- API is bound to localhost.
- PostgreSQL and Redis are not intentionally publicly exposed.
- API and Worker run from an immutable backend image.
- Production API and Worker do not use backend source-code bind mounts.

The Git working directory on the server is not itself the deployed backend
artifact. Editing repository source does not automatically modify the running
API or Worker.

For exact verified commit, image, migration, open operational items, and Pilot
state, use `docs/CURRENT_STATE.md`.

## 5. Ownership and Decision Authority

The Owner retains final authority over:

- repository ownership;
- infrastructure ownership;
- business/domain decisions;
- Production access approval;
- release approval;
- database migration approval;
- destructive operations;
- security-sensitive changes;
- Pilot acceptance;
- final release acceptance.

An engineer may investigate and propose changes without Production modification.

Material changes follow:

Audit -> Proposal -> Owner Approval -> Implementation -> Tests ->
Controlled Validation -> Owner Acceptance -> Release -> Monitoring.

Do not commit, push, tag, deploy, migrate, restart Production services, or
perform destructive Production operations without the required approval.

## 6. Access Handover

Access must be issued individually to the engineer. Do not transfer personal
accounts when dedicated access can be created.

Depending on responsibility, access may include:

- GitHub repository access;
- Production VPS SSH access;
- deployment environment access;
- monitoring access;
- DNS/domain access if required;
- backup location access if required;
- approved third-party integration access.

Apply least privilege.

Do not send long-lived secrets through repository files, source code, issue
comments, ordinary chat messages, or WhatsApp.

Secrets must be transferred through an approved secure channel or secret
management mechanism.

At engineer offboarding:

- remove repository access;
- remove/revoke SSH keys;
- revoke application/infrastructure credentials issued to that engineer;
- revoke third-party access;
- review active sessions/tokens;
- confirm no personal account remains operationally required.

The project must not depend on an engineer's personal GitHub, cloud, email,
domain, or infrastructure account.

## 7. First-Day Engineer Procedure

Before the first Production change, the incoming engineer should:

1. Read the mandatory documents.
2. Clone and inspect the repository.
3. Understand the backend and frontend directory structure.
4. Run the development environment where practical.
5. Identify the current Alembic head.
6. Understand the PostgreSQL RLS tenant-isolation model.
7. Understand authentication and RBAC.
8. Locate the automated tests and run an appropriate test set.
9. Review the release and rollback runbook.
10. Review backup and restore procedures.
11. Inspect Production read-only, if authorized.
12. Compare:
   - repository state;
   - approved release artifact;
   - database migration state;
   - running services.
13. Report discrepancies before changing anything.

The first Production action should not be used as the engineer's learning
exercise.

## 8. First-Week Takeover Plan

The first week should focus on proving safe transferability, not adding features.

Expected outcomes:

### Architecture comprehension

The engineer can explain:

- modular-monolith boundaries;
- backend module structure;
- frontend structure;
- database architecture;
- tenant isolation;
- authentication;
- RBAC;
- background jobs;
- deployment topology.

### Development capability

The engineer can:

- run the system locally;
- locate and run relevant tests;
- trace an API request from route to application/domain/infrastructure layers;
- identify frontend-to-backend integration points;
- create a safe development branch;
- explain the migration workflow.

### Operational capability

The engineer can explain or demonstrate safely:

- how Production is deployed;
- how logs are inspected;
- how health is checked;
- how backups are verified;
- how a release artifact is identified;
- how a release is validated;
- how rollback decisions are made.

### Real issue comprehension

As a takeover exercise, the engineer should independently review the current
Pilot blocker recorded in `docs/CURRENT_STATE.md`.

The engineer should:

1. reproduce or verify the issue safely;
2. identify the root cause;
3. explain the affected frontend/backend behavior;
4. propose the smallest safe fix;
5. propose regression tests;
6. stop for approval before Production modification.

## 9. Engineering Rules

The expected engineering cycle is:

Understand -> Reproduce -> Test -> Change -> Test -> Review -> Deploy ->
Verify -> Rollback if required.

Not:

Find bug -> edit Production -> hope it works.

Mandatory rules include:

- no blind `git reset --hard`;
- no blind `git clean`;
- no destructive `docker compose down -v`;
- no unreviewed `alembic downgrade`;
- no manual modification of `alembic_version`;
- no deletion of Production data for testing;
- no secrets committed to Git;
- no direct Production source editing as a normal deployment method;
- no schema migration without migration review and verified backup;
- no accounting or inventory change without business-integrity testing;
- no tenant-scoped feature without tenant-isolation consideration.

## 10. Database and Migration Responsibility

Before changing database schema, the engineer must understand:

- current Production Alembic revision;
- target code Alembic head;
- every migration being introduced;
- schema compatibility with previous application code;
- backup state;
- rollback/data-preservation strategy.

Do not assume Alembic downgrade is safe.

Database restore is not an ordinary application rollback because customer
transactions created after the backup may be lost.

Use the migration and recovery documents referenced by `/AGENTS.md`.

## 11. Multi-Tenancy and Security

Tenant isolation is a release-critical property.

The engineer must understand PostgreSQL Row-Level Security and the application's
tenant/company context mechanisms before modifying tenant-scoped data access.

Security-sensitive areas include:

- authentication;
- JWT/session behavior;
- password reset;
- RBAC;
- RLS;
- pre-authentication database access;
- audit logging;
- secret handling;
- infrastructure exposure.

Security, tenant-isolation, accounting-integrity, inventory-integrity, and
data-integrity regressions are release blockers.

## 12. Release Standard

A normal controlled release should establish:

1. exact approved Git commit;
2. exact release artifact;
3. current and target database revision;
4. migration review;
5. verified backup;
6. previous known-good release artifact;
7. Owner approval;
8. controlled deployment;
9. health validation;
10. Worker validation;
11. authentication validation;
12. changed-business-workflow smoke test;
13. log review;
14. Owner acceptance;
15. monitoring after release.

Follow `docs/RELEASE-RUNBOOK.md`; this section is only a summary.

## 13. Backup, Recovery, and Rollback

The incoming engineer must know where the approved procedures are and be able
to explain the difference between:

- application rollback;
- schema-compatible rollback;
- corrective migration;
- database restore;
- infrastructure recovery.

Do not restore a Production database merely to roll back application code.

A Production rollback drill must not be claimed as tested unless it has actually
been executed and recorded.

## 14. Open Issues and Pilot Work

Do not maintain a second independent list of current blockers in this document.

The authoritative current operational and Pilot issue snapshot is:

`docs/CURRENT_STATE.md`

At handover, the engineer must read that file and identify:

- current Pilot blockers;
- security follow-ups;
- deployment limitations;
- migration limitations;
- operational cleanup items.

New feature development should not displace Pilot blockers, security,
accounting integrity, inventory integrity, tenant isolation, or data integrity.

## 15. Recommended Engineer Profile

Recommended role:

**Senior Full-Stack Engineer — Python/FastAPI + Next.js + PostgreSQL**

A strong Senior Backend Engineer with substantial frontend and Production
experience may also fit.

Practical Production experience is more important than title alone.

A useful target is approximately 5+ years of relevant professional experience,
provided the engineer can demonstrate ownership of real Production systems.

### Must-have capability

The engineer should be comfortable with:

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- transactions and relational data integrity
- Alembic
- REST APIs
- Next.js / React
- TypeScript
- Docker / Docker Compose
- Linux / Ubuntu
- Nginx
- Git / GitHub
- authentication and authorization
- RBAC
- multi-tenant SaaS concepts
- automated testing
- Production debugging
- backup/recovery concepts
- web security fundamentals

### Preferred capability

Useful additional experience includes:

- Redis
- Celery
- PM2
- ERP systems
- accounting systems
- inventory systems
- SaaS platforms
- ZATCA / Saudi e-invoicing
- CI/CD
- OWASP practices
- observability and performance profiling

ERP/accounting experience is particularly valuable because technically valid
code can still produce financially incorrect business behavior.

## 16. Hiring Technical Evaluation

Do not evaluate a candidate only by asking them to build a new feature.

A useful 60–90 minute review exercise is to give the candidate read-only access
to the relevant repository material and ask them to explain:

1. the architecture;
2. tenant isolation;
3. migration strategy;
4. current deployment model;
5. rollback risks;
6. three technical/operational risks they notice;
7. how they would investigate the current Pilot blocker;
8. what regression test they would add.

The candidate should not modify Production during this exercise.

Useful interview questions include:

- How would you prove one tenant cannot read another tenant's data?
- What would you do if a Production migration fails halfway?
- How would you roll back an application release if new customer transactions
  already exist?
- How would you prevent a double submission from double-posting a financial
  transaction?
- What is the difference between application-level tenant filtering and
  PostgreSQL RLS?
- How would you test a change that affects both inventory and accounting?
- How would you prove that the Git checkout on a server matches what is
  actually running?

Strong answers should emphasize evidence, data preservation, reproducibility,
tests, least privilege, and controlled releases.

## 17. Handover Acceptance Checklist

Technical handover is not complete merely because repository credentials were
sent to the engineer.

Before declaring handover complete, verify that the engineer can:

- [ ] access the repository using their own approved identity;
- [ ] explain the system architecture;
- [ ] explain the Production topology;
- [ ] run the project in a safe development environment;
- [ ] locate and run relevant automated tests;
- [ ] identify the current Alembic revision/head;
- [ ] explain RLS tenant isolation;
- [ ] explain authentication and RBAC;
- [ ] locate application/Worker/Nginx logs;
- [ ] explain the backup verification process;
- [ ] explain the restore procedure in a safe environment;
- [ ] identify an immutable backend release artifact;
- [ ] explain the frontend PM2/standalone deployment model;
- [ ] follow the release runbook;
- [ ] explain rollback decision cases;
- [ ] diagnose a real issue without modifying Production unsafely;
- [ ] identify current Pilot blockers from `docs/CURRENT_STATE.md`;
- [ ] demonstrate that no operational dependency exists on a previous
      engineer's personal account or private chat history.

The Owner should accept the handover only after the required items are
demonstrated.

## 18. What Must Be Handed to the Engineer

The handover package should include:

### In the repository

- source code;
- architecture documentation;
- developer documentation;
- current-state snapshot;
- testing guidance;
- release/rollback runbook;
- database/migration documentation;
- tenant-isolation documentation;
- disaster-recovery documentation;
- this handover guide.

### Separately and securely

Only when required by the engineer's responsibilities:

- individual GitHub access;
- individual SSH access;
- Production access instructions;
- monitoring access;
- backup access;
- DNS/domain access;
- third-party integration credentials.

Never place these secrets in the repository.

## 19. Handover Completion Record

When responsibility is formally transferred, record outside secrets:

- handover date;
- outgoing responsible party;
- incoming responsible engineer;
- repository access confirmed;
- infrastructure access confirmed;
- mandatory reading completed;
- development environment verified;
- Production topology understood;
- backup/recovery procedure understood;
- release/rollback procedure understood;
- current blockers reviewed;
- acceptance checklist completed;
- Owner acceptance.

Do not record passwords, tokens, private keys, or secret values in the
completion record.

## 20. Final Principle

The goal of handover is not for the incoming engineer to memorize the system.

The goal is that a qualified engineer can independently establish the truth,
make controlled changes, prove those changes with tests and runtime evidence,
protect customer data, and safely transfer responsibility again in the future.
