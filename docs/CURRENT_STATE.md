# Alfahd ERP — Current Verified State

> This document is the operational handoff snapshot for human engineers and AI coding agents.
> Update it whenever a material Production, architecture, deployment, migration, or release-state change is accepted.
> Do not store secrets in this file.

## 1. Current Phase

Phase 2 — Pilot Release & Commercial Readiness.

Immediate objective: safely onboard the first 5–10 real Pilot companies before broad commercial scaling.

Current Pilot focus: onboarding reliability and business acceptance testing.

## 2. Production Baseline

- Repository branch: `main`
- Verified Production repository HEAD: `be53eef02ed3e03d1ae3f98fa3f156f8a73ae8a2`
- Backend release image: `alfahd-erp-backend:6dac48f`
- Backend image ID: `sha256:7b42b44a7b447565ce1b2dddcc713f7d16ad8bf4b7a615505667d8844c8abd7f`
- Verified Alembic database revision: `687d818314fd`
- Verified code Alembic head: `687d818314fd`
- Database revision and code migration head are aligned as last verified.

The Production repository contains known untracked operational files:

- `frontend/get-docker.sh`
- `infra/docker-compose.yml.pre-monitoring`

Do not use blind `git reset --hard`, `git clean`, or other destructive cleanup commands.

## 3. Actual Production Topology

Production uses a hybrid host/container deployment model:

- Host Nginx terminates HTTPS and reverse proxies traffic.
- Next.js frontend runs on the host under PM2.
- Frontend PM2 process: `alfahd-frontend`.
- Frontend runtime: `.next/standalone/server.js`.
- FastAPI API runs in Docker Compose.
- Celery worker runs in Docker Compose.
- PostgreSQL runs in Docker Compose.
- Redis runs in Docker Compose.
- API host binding is restricted to localhost.
- PostgreSQL and Redis are not intentionally exposed publicly.
- API and Worker run from the immutable image `alfahd-erp-backend:6dac48f`.
- API and Worker have no backend source-code bind mounts (`mounts=0` at the last verification).

The verified runtime takes precedence over older documentation if a conflict exists.

## 4. Release / Rollback Status

The backend immutable-release cutover has been completed and validated.

Verified state:

- API and Worker run from the same immutable backend image.
- Backend source is not bind-mounted into the application containers.
- Previous pre-immutable API and Worker images were preserved as rollback artifacts before cutover.
- Public `/health` passed after cutover.
- Celery worker responded successfully after cutover.
- Application rollback preparation is complete.
- An actual Production rollback drill after the immutable cutover has NOT been performed.

Frontend deployment remains host-based through PM2 and requires explicit handling of Next.js standalone static assets.

Database rollback must never assume that `alembic downgrade` is safe.

See `docs/RELEASE-RUNBOOK.md` for the controlled release and rollback procedure.

## 5. Backup / Restore

Pilot backup and restore controls have been validated:

- Automated database backup is configured through systemd.
- Backup integrity uses SHA-256 verification.
- A real restore test to a temporary database has passed.
- An off-host backup copy has been verified.
- A verified backup is required before Production schema migrations and releases that can affect data.

See `docs/21-disaster-recovery-and-rollback.md`.

## 6. Monitoring

Pilot monitoring baseline is operational:

- Docker log rotation is configured for persistent services.
- Public `/health` returns application/database health.
- External uptime monitoring is configured.
- Nginx and application logs remain available for incident investigation.

Advanced APM/metrics remain deferred unless Pilot evidence requires them.

## 7. Current Pilot / Operational Open Items

### Pilot blocker

`PILOT-01A — Company Profile Resume / Idempotency`

Observed during new-company onboarding:

- Initial company bootstrap succeeded.
- A Company Profile was created.
- A repeated profile save attempted another create and the backend correctly rejected the duplicate.
- The Step 2 frontend currently invokes `createProfileMutation` when saving the profile.
- After browser refresh, the wizard returned to Step 2 with an empty/default form instead of reliably resuming the existing profile.
- Required work: reproduce under test, confirm root cause, design the resume/create/update behavior, add regression tests, obtain Owner approval, implement, and validate.

Do not alter Production data merely to bypass this state; it is useful regression-test evidence.

### Other open operational items

- Formalize the Next.js standalone release procedure including `.next/static` and `public` handling.
- Resolve or deliberately redesign the currently unsuitable Compose migration-service path before relying on it in Production.
- Decide the disposition of the known untracked operational files without blind deletion.
- Rotate/revoke previously exposed credentials/sessions as appropriate.
- Review the duplicate Nginx HTTP server-name warning.
- Verify Next.js security/update status from authoritative upstream sources before changing versions.
- Keep release/rollback documentation synchronized with the immutable backend deployment.
- Complete the human-engineer handoff package.

## 8. Human / AI Handoff Principle

The repository must remain transferable between professional human engineers, Claude, Codex, ChatGPT, or other approved engineering tools.

No critical architecture, deployment, security, database, recovery, or operational knowledge may exist only in private chat history or an individual engineer's memory.

Repository documentation plus verified runtime evidence are the source of truth.

Start with `/AGENTS.md`, then this file, then the documents referenced by `/AGENTS.md`.

## 9. Change Governance

For material changes:

Audit -> Proposal -> Owner Approval -> Implementation -> Tests -> Controlled Validation -> Owner Acceptance -> Release -> Monitoring.

Do not commit, push, tag, deploy, migrate, restart Production services, or perform destructive actions without the required approval.
