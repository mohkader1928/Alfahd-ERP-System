# Alfahd ERP — Current Verified State

> This document is the operational handoff snapshot for human engineers and AI coding agents.
> Update it whenever a material Production, architecture, deployment, migration, or release-state change is accepted.
> Do not store secrets in this file.

## 1. Current Phase

Phase 2 — Pilot Release & Commercial Readiness.

Immediate objective: safely onboard the first 5–10 real Pilot companies before broad commercial scaling.

## 2. Production Baseline

- Repository branch: `main`
- Verified Production commit: `d638a0c`
- Commit purpose: INV-002 Cycle Count inventory-adjustment accounting fix
- Verified Alembic database revision: `687d818314fd`
- Verified code Alembic head: `687d818314fd`
- Database revision and code migration head are aligned.

Production working tree is not clean. Do not use blind `git reset --hard` or `git clean`.

## 3. Actual Production Topology

Production currently uses a hybrid deployment model:

- Host Nginx terminates HTTPS and reverse proxies traffic.
- Next.js frontend runs on the host under PM2.
- Frontend PM2 process: `alfahd-frontend`
- Frontend runtime: `.next/standalone/server.js`
- FastAPI API runs in Docker Compose.
- Celery worker runs in Docker Compose.
- PostgreSQL runs in Docker Compose.
- Redis runs in Docker Compose.
- API host binding is restricted to localhost.
- PostgreSQL and Redis are not intentionally exposed publicly.

The actual Production topology takes precedence over older deployment documentation if a conflict exists.

## 4. Release / Rollback Status

Release and rollback design has been audited.

Current limitations:

- API and Worker currently use Docker images tagged only as `latest`.
- No previous Docker release image is currently retained.
- Versioned release images are required before the next Pilot release.
- Frontend standalone deployment requires explicit handling of `.next/static`.
- `frontend/public` exists but is not currently present inside the standalone deployment directory.
- Production contains local operational changes that must not be destroyed by blind Git rollback.
- Database rollback must not assume that `alembic downgrade` is safe.

See `docs/RELEASE-RUNBOOK.md` for the executable procedure once completed.

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
- Public `/health` endpoint returns application/database health.
- External uptime monitoring is configured.
- Nginx and application logs remain available for incident investigation.

Advanced APM/metrics are deferred unless Pilot evidence requires them.

## 7. Important Open Operational Items

- Complete `docs/RELEASE-RUNBOOK.md`.
- Introduce versioned API/Worker Docker release images.
- Formalize the Next.js standalone release procedure including static/public assets.
- Resolve or deliberately redesign the currently unsuitable Compose migration-service path before relying on it.
- Review Production working-tree operational changes and decide how they should be preserved/versioned.
- Rotate/revoke previously exposed credentials/sessions as appropriate.
- Review the duplicate Nginx HTTP server-name warning.
- Verify Next.js security/update status from authoritative upstream sources before changing versions.

## 8. Handoff Principle

The repository must remain transferable between Claude, Codex, other AI coding agents, and professional human engineers.

No critical operational knowledge may exist only in private chat history.

Start with `/AGENTS.md`, then use this file as the current-state snapshot.

## 9. Change Governance

For material changes:

Audit -> Proposal -> Owner Approval -> Implementation -> Tests -> Controlled Validation -> Owner Acceptance -> Release -> Monitoring.

Do not commit, push, tag, deploy, migrate, restart Production services, or perform destructive actions without the required approval.
