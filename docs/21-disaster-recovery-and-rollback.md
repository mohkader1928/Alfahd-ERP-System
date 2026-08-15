# Phase 21 — Disaster Recovery & Rollback Runbook

Stage 0 (Adaptive ERP — Golden Baseline Protection) deliverable. This is a
step-by-step operational runbook for the **owner or any future developer**,
written to be followed **without Claude or any AI assistant** — every
command is literal and copy-pasteable, every credential referenced by name
only (never printed), and every step states what to check before moving to
the next one.

Companion files:
- [`docs/22-release-manifest-v1.0.0.md`](22-release-manifest-v1.0.0.md) — exact identity of the `v1.0.0` baseline (SHA, tag, migration head, versions).
- `infra/backup/backup_db.sh` — takes a backup (Step 1 below).
- `infra/backup/restore_db.sh` — restores a backup (Step 4 below).

Both scripts stream data over Docker's stdin/stdout rather than writing
temp files inside the container — this is deliberate: on Windows, Git
Bash/MSYS silently rewrites container-internal paths like `/tmp/foo` into
host paths before they reach `docker exec`, which breaks inside the Linux
container. Streaming avoids the whole class of bug. If you ever edit these
scripts, keep that pattern.

---

## 1. How to take a backup

```bash
cd erp-system
bash infra/backup/backup_db.sh
```

What it does: runs `pg_dump -Fc` (Postgres's custom archive format) inside
the running `erp-nucleus-postgres-1` container, streams the result straight
to a host file, and writes a SHA256 checksum next to it. It is **read-only**
against the source database — safe to run at any time, including against a
live system with users on it.

Override the target if you're backing up a different environment:
```bash
CONTAINER=<postgres-container-name> DB_USER=<role> DB_NAME=<db> bash infra/backup/backup_db.sh
```

**When to run this**: before every deploy, before every migration, on a
schedule (daily, via cron/Task Scheduler once you have one — none exists
yet, see [Known limitations](#known-limitations-carried-into-this-doc)),
and any time you're about to do something to the database you're not 100%
sure about.

## 2. Where backups are stored

`infra/backup/artifacts/` — gitignored on purpose (backups are large,
environment-specific, and may contain real customer data; they must never
be committed to git). Filenames are `erp_nucleus_<UTC-timestamp>.dump`, e.g.
`erp_nucleus_20260815T143951Z.dump`, each with a `.sha256` sidecar.

**This directory lives only on whatever machine you ran the script on.**
Nothing here copies backups off-host automatically — for a production
deployment, add a step that copies the `.dump` file to off-host storage
(object storage, a second disk, wherever) right after step 1 completes.
That off-host copy step does not exist yet; treat it as a prerequisite
before you trust this procedure for a real production database, not just a
dev one.

## 1a. Off-host backup (keeping a copy that survives losing this machine)

A local `.dump` file only protects you if *this disk* survives. `infra/backup/copy_offhost.sh` copies the most recent backup to any destination path you point it at — an external drive, a mapped network/NAS share, or a locally-synced cloud-storage folder (OneDrive, Dropbox, Google Drive, etc. — once synced, these are all just ordinary filesystem paths, so this needs **no cloud API and no credentials**):

```bash
DEST_DIR="D:/erp-backups" bash infra/backup/copy_offhost.sh
DEST_DIR="//nas-box/backups/erp" bash infra/backup/copy_offhost.sh
DEST_DIR="D:/erp-backups" RETENTION=14 bash infra/backup/copy_offhost.sh   # also prune to the 14 most recent
```

It verifies the copy is byte-identical (size check + SHA256, if a `.sha256` sidecar exists) before declaring success — a copy that silently truncated is worse than no copy, because it looks like it worked.

**Honest status as of Stage 0 Closure**: this script's logic was tested and works (copy + checksum verification + retention pruning, verified against a local test directory). **No genuinely off-host copy has actually been made** — this development machine has no external drive, mapped NAS share, or cloud-sync folder configured in this session to point `DEST_DIR` at. This is not something to fake: run the command above yourself, pointed at wherever you actually want a second copy to live, the first time you have one available. If your chosen destination needs real credentials (e.g. a cloud provider's API instead of a synced folder), do not put them in this repo or in this script — read them from an environment variable at run time on the machine that runs the backup, the same pattern every other credential in this project already follows (§12 of `20-developer-guide.md`).

**Retention**: `RETENTION=<N>` on `copy_offhost.sh` keeps the N most recent backups at the destination and deletes older ones. Pick N based on how far back you might need to recover and how much space you have — there's no single right answer; 14 daily backups (two weeks) is a reasonable starting point for a small system like this one.

**Backup verification**: `backup_db.sh` already verifies structural validity (`pg_restore --list`) and writes a SHA256 checksum at creation time (§3 below). `copy_offhost.sh` re-verifies that checksum after every copy.

**Restore verification**: verifying a backup opens != verifying it *restores correctly*. Periodically (monthly is reasonable) actually run the restore procedure (§4) into a throwaway container, the same way Stage 0 did — do not assume a checksum-valid backup is a restorable one; only actually restoring it proves that.

**Recommended frequency**: daily, plus always immediately before a deploy or migration (§1's own "when to run this"). More frequent than daily is reasonable once real customer data exists and every day of loss matters more.

## 1b. Automating the backup (so it doesn't depend on a human remembering)

Two ready-to-run options — pick whichever matches how this is actually deployed. **Neither is registered automatically by this repo** — a recurring scheduled task is a standing change to the machine it runs on, and enabling it is a deliberate decision for whoever operates that machine to make, not something to switch on silently. Copy-paste the command for your platform when you're ready:

**Windows (Task Scheduler)** — runs daily at 02:00, backup then off-host copy:
```powershell
schtasks /create /tn "ERP Nightly Backup" /tr "\"C:\Program Files\Git\bin\bash.exe\" -c \"cd '/c/Users/L/Desktop/claude apps/erp-system' && bash infra/backup/backup_db.sh && DEST_DIR='D:/erp-backups' RETENTION=14 bash infra/backup/copy_offhost.sh\"" /sc daily /st 02:00
```
Adjust the repo path and `DEST_DIR` for your actual setup. Verify it's registered: `schtasks /query /tn "ERP Nightly Backup"`. Remove it: `schtasks /delete /tn "ERP Nightly Backup" /f`.

**Linux/WSL/production server (cron)** — same schedule:
```cron
0 2 * * * cd /path/to/erp-system && bash infra/backup/backup_db.sh && DEST_DIR=/mnt/erp-backups RETENTION=14 bash infra/backup/copy_offhost.sh >> /var/log/erp-backup.log 2>&1
```
Add via `crontab -e`.

Both options: (1) require nothing beyond what's already in this repo, (2) run with no AI/Claude involved at all, (3) log their own output, so a failure is visible without needing anyone to have been watching when it ran.

## 3. How to verify a backup

The backup script already does this automatically (`pg_restore --list`
against the file, which reads the archive's table of contents without
restoring anything — proves the file is structurally valid). To re-verify
an existing file by hand:

```bash
docker exec -i erp-nucleus-postgres-1 pg_restore --list < infra/backup/artifacts/erp_nucleus_<timestamp>.dump | head -20
sha256sum -c infra/backup/artifacts/erp_nucleus_<timestamp>.dump.sha256
```

Both must succeed without error. `pg_restore --list` should print a long
list of `CREATE TABLE`/`COPY`/`CONSTRAINT` entries; if it errors, the dump
is corrupt and you need an earlier backup.

## 4. How to restore a backup

**Read this whole section before running anything.** `restore_db.sh` is
destructive to whatever's already in the *target* database
(`pg_restore --clean --if-exists`) — that's exactly what you want when
restoring onto a fresh/broken instance, and exactly what you don't want if
you point it at a database you care about by mistake.

```bash
bash infra/backup/restore_db.sh infra/backup/artifacts/erp_nucleus_<timestamp>.dump
```

By default this targets `erp-nucleus-postgres-1` / database `erp_nucleus`
— i.e. your real dev/prod Postgres container. Override for anything else
(and **always** override when just testing a restore):

```bash
TARGET_CONTAINER=<container> DB_NAME=<db> bash infra/backup/restore_db.sh <dump-file>
```

After it finishes, two things are still needed before the app can run
against the restored database (a `pg_dump` of one database does **not**
include Postgres roles — those are cluster-level):

```bash
# 1. Re-create/re-assert the erp_migrate / erp_app roles (idempotent —
#    safe to run even if they already exist with the right passwords).
#    Needs the SAME bootstrap-role credentials + role passwords you'd put
#    in backend/.env.migrate(.production) — see docs/17c-rls-runtime-role-hardening.md.
docker run --rm --network <network> \
  -e DATABASE_URL_BOOTSTRAP_SYNC="postgresql://<bootstrap_user>:<bootstrap_password>@<postgres-host>:5432/<db>" \
  -e POSTGRES_DB=<db> \
  -e ERP_MIGRATE_PASSWORD="<erp_migrate_password>" \
  -e ERP_APP_PASSWORD="<erp_app_password>" \
  <api-image> python -m src.scripts.bootstrap_db_roles

# 2. Confirm the restored schema is at the expected migration head (see
#    Step 6 below) before pointing a real api/worker at it.
```

**Restoring onto a genuinely fresh Postgres instance** (disaster recovery,
not just a test) — same two commands above, run against the new instance,
then start `api`/`worker` normally.

## 5. How to restart the ERP

Normal restart (no code/schema change):
```bash
cd infra
docker compose -f docker-compose.yml restart api worker    # dev
docker compose -f docker-compose.prod.yml restart api worker    # prod
```

Full cold start from nothing (see [`docs/14-deployment.md`](14-deployment.md) §4 for the
complete prod version):
```bash
cd infra
docker compose -f docker-compose.yml up -d postgres redis
docker compose -f docker-compose.yml --profile tools run --rm migrate
docker compose -f docker-compose.yml up -d api worker
```

## 6. How to verify migration state

```bash
# What the database currently thinks its schema version is:
docker exec erp-nucleus-postgres-1 psql -U erp -d erp_nucleus -c "SELECT version_num FROM alembic_version;"

# What the current codebase's migration files say the head *should* be —
# run this from inside a container built from that codebase (has alembic
# installed; the host machine generally doesn't):
docker run --rm <api-image> alembic heads
```

**These two values must match.** If they don't: either migrations need to
be run (`docker compose --profile tools run --rm migrate`), or you're
looking at the wrong database/checkout. Never resolve a mismatch by editing
the `alembic_version` table by hand — find out *why* it doesn't match
first.

As of `phase-one-v1.0.0` the head is `a8b9c0d1e2f3` — see
[`docs/22-release-manifest-v1.0.0.md`](22-release-manifest-v1.0.0.md).

## 7. How to verify application health

```bash
curl -s http://localhost:8000/health
# Expected: {"status":"ok","database":true}
```

`database: false` (or no response) means the API process is up but can't
reach Postgres — check `DATABASE_URL`/`DATABASE_URL_SYNC` in
`backend/.env`(`.production`) and that the `postgres` service is healthy
(`docker compose ps`).

For a deeper check (proves auth, RBAC, and company isolation are actually
working, not just that a process is listening): run the automated test
suite's isolation-focused files against the environment in question —
```bash
docker exec <api-or-worker-container> pytest -q tests/test_multi_tenancy_isolation.py tests/test_rls_enforcement.py
```
(only if `tests/` is present in that container/image — it's intentionally
excluded from the production image via `backend/.dockerignore`; copy it in
with `docker cp backend/tests <container>:/app/tests` first if needed, the
same way Stage 0's own restore-test verification did — see the Stage 0
Final Report for the exact commands used).

## 8. How to roll back to a previous release

Every release should exist as a tagged, buildable commit (this is why
[`docs/22-release-manifest-v1.0.0.md`](22-release-manifest-v1.0.0.md) exists — extend that
pattern for every future release, not just v1.0.0).

```bash
git checkout <previous-release-tag>
cd infra
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d api worker frontend
```

**Migrations**: this project's migrations have been additive-only for its
entire history so far (confirmed: single linear chain, 50 files, no
branching, no destructive `downgrade()` path has ever been exercised in
practice — see `docs/14-deployment.md` §4). That means rolling back
*code* to an older release while the *database* is already on a newer
schema is usually safe (older code simply doesn't use the newer
columns/tables) — but this has not been tested end-to-end for every
migration, so treat it as "probably fine," not "proven," and prefer
restoring a matching-era backup (§4) over trusting a code-only rollback
when the schema has actually changed since.

## 9. How to roll back specifically to v1.0.0

```bash
git checkout phase-one-v1.0.0
```
This alone reconstructs the exact source tree (confirmed reproducible —
see the manifest). If the database also needs to go back to its v1.0.0-era
state (not just the code), you need a backup taken at that time — Stage 0
is when backup/restore tooling was first introduced, so **no pre-v1.0.0
database backup exists**. Going forward, take a backup (§1) before every
release from here on, so this option is real for every future release
including the one right after v1.0.0.

If only the *code* needs to go back (database schema is compatible or
ahead per the additive-migrations note in §8):
```bash
git checkout phase-one-v1.0.0
cd infra && docker compose -f docker-compose.prod.yml build && docker compose -f docker-compose.prod.yml up -d
```

## 10. What NOT to do in an emergency

- **Do not** run `alembic downgrade` without first reading every
  migration's `downgrade()` function between the current head and the
  target — several early migrations were written additive-only and their
  downgrade path has never been exercised against real data.
- **Do not** manually edit the `alembic_version` table to "fix" a mismatch
  — find the actual cause first (§6).
- **Do not** restore a backup into the *live* container/database unless
  you have already accepted that this destroys current data
  (`restore_db.sh` uses `--clean`, i.e. it drops existing objects first).
  Always restore into an isolated target first if there's any doubt.
- **Do not** run `docker compose down -v` (or any command that removes
  volumes) as a troubleshooting step — this deletes the Postgres data
  volume permanently, with no confirmation prompt.
- **Do not** connect application traffic to the database using the
  bootstrap superuser role (`erp`/`POSTGRES_USER`) even temporarily "to fix
  something quickly" — it bypasses every RLS policy unconditionally (see
  `docs/17c-rls-runtime-role-hardening.md`), silently disabling company
  isolation for the duration.
- **Do not** commit anything from `infra/backup/artifacts/` to git.
- **Do not** treat "the API responds" as proof the database is intact —
  always check `/health`'s `database` field and, for anything
  security-relevant, the isolation test files (§7).
- **Do not** assume an AI assistant (Claude or otherwise) is available or
  needed to execute any step in this document. Every command above is
  meant to be run directly by a human, from this file alone.

---

## Known limitations carried into this doc

- No automated/scheduled backups exist yet — §1 must currently be run
  manually. Automating it (cron, Task Scheduler, or a CI job) is a natural
  next step, not done as part of Stage 0.
- No off-host backup copy step exists yet (§2).
- Code-rollback-without-a-matching-backup (§8) is a reasonable-confidence
  claim based on the migration history being additive-only so far, not a
  tested guarantee for every possible migration.
- This runbook assumes Docker Compose deployment, matching
  `docs/14-deployment.md`. If the deployment method ever changes, this
  file needs a corresponding update.
