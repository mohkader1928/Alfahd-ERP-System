# Alfahd ERP — Production Release & Rollback Runbook

> Operational runbook for human engineers and AI coding agents.
> Read `/AGENTS.md` and `docs/CURRENT_STATE.md` before using this document.
> Never store secrets in this file.

## 1. Purpose

Provide a repeatable, auditable, and data-safe procedure for releasing and rolling
back Alfahd ERP Production.

Primary principles:

- Protect customer data before protecting deployment speed.
- Never assume database migrations are reversible.
- Never rely on private chat history for release knowledge.
- Every release must identify the exact Git commit, database revision, application
  artifacts, validation evidence, and rollback point.
- Production changes require Owner approval.

## 2. Deployment Modes

### CURRENT — Verified Production State

Production currently uses a hybrid deployment:

- Nginx runs on the host and terminates HTTPS.
- Next.js frontend runs on the host under PM2 as `alfahd-frontend`.
- Frontend entry point is `.next/standalone/server.js`.
- API, Celery worker, PostgreSQL, and Redis run through Docker Compose.
- API and Worker use `../backend:/app` bind mounts.
- Current Compose therefore runs source-mounted backend code.
- API is bound to `127.0.0.1:8000`.
- PostgreSQL and Redis are not intentionally exposed publicly.

The current API/Worker deployment must NOT be treated as an immutable-image release.

### TARGET — Immutable Pilot/Production Deployment

Target deployment:

1. Select an approved Git release commit/tag.
2. Build API/Worker from the Dockerfile `production` stage.
3. Tag release artifacts with an immutable release identifier.
4. Do not bind-mount backend source into Production application containers.
5. Preserve the previous known-good release artifacts.
6. Deploy only after backup, migration review, and validation gates pass.

IMPORTANT:
The transition from CURRENT to TARGET is a separate controlled infrastructure change.
This runbook does not authorize an agent or engineer to perform that transition
without explicit Owner approval and validation.

## 3. Release States

A release may be:

- `PROPOSED` — prepared but not approved.
- `APPROVED` — Owner approved for controlled release.
- `DEPLOYING` — Production change in progress.
- `VALIDATING` — deployment complete; acceptance checks running.
- `ACCEPTED` — checks passed and release accepted.
- `ROLLED_BACK` — application returned to previous known-good release.
- `FAILED` — release stopped; incident/rollback decision required.


## 4. Pre-Release Gate

Before any Production release:

- Confirm Owner approval.
- Record the exact Git commit intended for release.
- Record `git status`; do not overwrite unrelated local changes.
- Record the current Production Git commit.
- Record the current database Alembic revision.
- Confirm the target code Alembic head.
- Review every migration between current DB revision and target head.
- Confirm the previous known-good application release.
- Create and verify a fresh database backup.
- Confirm sufficient disk space.
- Confirm current `/health` is healthy before changing anything.
- Confirm PostgreSQL and Redis are healthy.
- Confirm the frontend PM2 process is online.
- Define the rollback decision before deployment starts.

If any required item is unknown or fails, STOP the release.


## 5. Backup and Migration Gate

Before applying any Production database migration:

- Create a fresh database backup.
- Verify the backup integrity/checksum.
- Record the backup location and timestamp.
- Record the current Alembic revision.
- Record the target Alembic head.
- Review the migration for destructive or irreversible operations.
- Determine whether old application code remains compatible with the migrated schema.
- Define the data-preserving rollback strategy before migration.

Never use an unreviewed `alembic downgrade` as the default rollback method.
Never manually change `alembic_version` to simulate a rollback.

Restoring a database backup is a last-resort recovery action because transactions
created after that backup may be lost.

If migration safety or rollback compatibility is uncertain, STOP the release.


## 6. Application Release Procedure

### 6.1 Backend — CURRENT Immutable Mode

Production API and Worker now run from an approved immutable backend image.

Last verified runtime state:

- API image: `alfahd-erp-backend:6dac48f`
- Worker image: `alfahd-erp-backend:6dac48f`
- API and Worker use the same verified image artifact.
- Backend source is not bind-mounted into either application container.
- The immutable cutover has been completed and validated.
- Previous pre-immutable API and Worker images were preserved as rollback artifacts.
- An actual Production rollback drill after this cutover has NOT been performed.

For an approved backend release:

1. Select and record the exact approved Git commit.
2. Build from the Dockerfile `production` stage.
3. Tag the release artifact with a unique immutable release identifier.
4. Verify that secrets or environment files are not embedded in the image.
5. Complete the backup and migration gate in Section 5.
6. Preserve the previous known-good application artifact.
7. Deploy API and Worker from the exact approved image.
8. Do not bind-mount backend source into Production API or Worker containers.
9. Run the validation and acceptance checks in Section 7.
10. Keep the previous known-good artifact until the release is accepted.

The Production repository working tree is not the deployed backend artifact.
Do not assume that changing files in the repository changes the running API or Worker.

### 6.2 Legacy Source-Mounted Mode

The previous Production model used `../backend:/app` source bind mounts.

That model is no longer the verified current backend deployment and must not be
silently reintroduced.

The preserved pre-immutable images and historical Git state exist for recovery
analysis, but rollback must follow Section 8 and must account for the deployment
mode, database compatibility, and customer data created after release.

Do not treat a Docker image tag alone as sufficient to reproduce the old
source-mounted runtime behavior.

### 6.3 Frontend — CURRENT Mode

The frontend runs under PM2 as `alfahd-frontend`.

For an approved frontend release:

- Record the current Git/release state.
- Run the approved Next.js production build.
- Verify the standalone output exists.
- Ensure `.next/static` is available to the standalone deployment.
- Ensure required `public` assets are available to the standalone deployment.
- Restart only `alfahd-frontend`.
- Verify PM2 reports the process online.
- Verify the public application through Nginx/HTTPS.

Do not delete the previous known-good frontend artifact until the new release
has passed validation.


## 7. Post-Release Validation and Acceptance

After deployment, enter `VALIDATING` state.

Required checks:

- Public `/health` returns HTTP 200.
- API reports database connectivity healthy.
- PostgreSQL and Redis are healthy.
- Celery Worker is running and able to process required tasks.
- Frontend PM2 process is online.
- Public HTTPS application loads successfully.
- Authentication works.
- Critical changed workflow is smoke-tested.
- No new critical errors appear in application, Worker, or Nginx logs.
- Database Alembic revision matches the expected release revision.
- Tenant isolation and data integrity must not regress.

For accounting, inventory, security, tenant-isolation, or migration changes,
perform the specific acceptance tests required by the changed area.

Only after required validation passes may the release become `ACCEPTED`.

If a release-blocking check fails, do not declare success. Enter `FAILED` and
use the rollback decision process in Section 8.


## 8. Rollback Decision Process

When a release fails, first determine what changed.

### Case A — Application Change, No Database Schema Change

Prefer application rollback.

- Preserve current customer data.
- Return backend/frontend to the previous known-good application release.
- Restart/recreate only affected services.
- Run Section 7 validation again.
- Do NOT restore the database merely to roll back application code.

### Case B — Migration Applied, Previous Code Is Schema-Compatible

If reviewed evidence confirms the previous application can safely operate on the
new schema:

- Roll back the application to the previous known-good release.
- Keep the migrated database.
- Validate application and data integrity.
- Schedule migration cleanup separately if required.

### Case C — Migration Applied, Compatibility Is Uncertain or Broken

STOP automated rollback.

- Do not run an unreviewed `alembic downgrade`.
- Do not manually alter `alembic_version`.
- Prevent further risky writes if data integrity is threatened.
- Review the exact migration and compatibility impact.
- Choose a data-preserving corrective migration when feasible.
- Use database restore only with explicit Owner approval and a documented
  assessment of transactions that may be lost.

### Case D — Infrastructure Failure

Restore only the affected infrastructure component to its previous known-good
configuration/artifact where possible.

Do not combine infrastructure rollback with database restore unless database
recovery is independently required.

### Rollback Completion

A rollback is complete only after:

- `/health` is healthy.
- Required services are healthy.
- Public HTTPS application works.
- Authentication works.
- Critical workflows pass smoke tests.
- Database revision/state is understood and recorded.
- No new critical errors are present.
- Owner is informed of the final state.

Record the release as `ROLLED_BACK` and document the failure before attempting
another Production release.
