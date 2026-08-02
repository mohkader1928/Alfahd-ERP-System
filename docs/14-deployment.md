# Phase 14 — Deployment

Scope: a containerized deployment package for the nucleus, matching the
topology already agreed in [08-system-architecture.md §9](08-system-architecture.md).
Per NFR-PORT-001, the same images run in cloud or on-premise — only
environment variables differ. This phase does **not** cover actual cloud
provisioning (no Terraform/cloud account was in scope) or Celery Beat
(nothing periodic exists in the nucleus yet) or the optional read replica
(explicitly deferred in the architecture doc until load requires it).

Everything below was built and then actually verified by building the
images, running migrations against a fresh database, booting the full
stack, and hitting it end-to-end through nginx (bootstrap → 201 Created) —
not just written and assumed correct.

## 1. What's new in `infra/`

```
infra/
  docker-compose.yml          # existing — local dev, unchanged
  docker-compose.prod.yml     # new — production topology
  nginx/nginx.conf            # new — reverse proxy: /api/* → backend, / → frontend
  .env                        # new, gitignored — compose-level vars (Postgres creds, ports)
```

Plus per-project additions:
- `backend/Dockerfile` — now multi-stage (`production` and `dev` targets;
  `dev` stays the default/last stage so the existing dev compose file needed
  no changes). Production target skips dev extras (pytest/ruff), doesn't
  bind-mount source, runs without `--reload`, and starts 4 uvicorn workers.
- `backend/.dockerignore`, `backend/.env.production` (gitignored — see §3)
- `frontend/Dockerfile` — new, two-stage build producing Next.js's
  `standalone` output (`next.config.ts` now sets `output: "standalone"`)
- `frontend/.dockerignore`, `frontend/.env.example`

## 2. Topology

```
Browser → nginx:80 → /api/*  → api:8000   (FastAPI, 4 workers)
                    → /*      → frontend:3000 (Next.js standalone)
worker  → postgres, redis, (ZATCA platform — outbound only)
```

`api` and `worker` share the same image (`target: production`) and the same
`.env.production` — they differ only in `command`. Scaling the API tier is
`docker compose -f docker-compose.prod.yml up -d --scale api=3`; nginx's
`upstream api_upstream { server api:8000; }` resolves through Docker's
embedded DNS and load-balances across however many replicas exist, no config
change needed (this is the NFR-SCALE-001 "stateless, horizontally scalable"
requirement from the architecture doc — sessions live in the JWT, not
server memory, so any replica can serve any request).

## 3. Secrets — what you must generate yourself

Nothing in this repo ships real production credentials. Two files are
gitignored and must exist before `docker compose -f docker-compose.prod.yml up` works:

**`backend/.env.production`** (copy `backend/.env.example` and fill in) —
the **runtime** credential (`erp_app`), used only by `api`/`worker`:
```
DATABASE_URL=postgresql+asyncpg://erp_app:<erp_app_password>@postgres:5432/<db>
DATABASE_URL_SYNC=postgresql+psycopg2://erp_app:<erp_app_password>@postgres:5432/<db>
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=<random, e.g. `python -c "import secrets; print(secrets.token_hex(32))"`>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
APP_ENV=production
LOG_LEVEL=INFO
CORS_ORIGINS=https://your-public-domain   # comma-separated if more than one; was hardcoded to localhost:3000 pre-Phase-16A
```

**`backend/.env.migrate.production`** (copy `backend/.env.migrate.example`
and fill in) — the **bootstrap** and **migration** credentials, used only
by the one-off `migrate` service; see
[17c-rls-runtime-role-hardening.md](17c-rls-runtime-role-hardening.md) for
why this is a separate file from the one above:
```
DATABASE_URL_BOOTSTRAP_SYNC=postgresql://<postgres_user>:<postgres_password>@postgres:5432/<db>
POSTGRES_DB=<db>
ERP_MIGRATE_PASSWORD=<erp_migrate_password>
ERP_APP_PASSWORD=<erp_app_password>          # must match backend/.env.production above
DATABASE_URL_MIGRATE_SYNC=postgresql+psycopg2://erp_migrate:<erp_migrate_password>@postgres:5432/<db>
```

**`infra/.env`** (compose-level — Postgres init + nginx port + frontend build arg):
```
POSTGRES_USER=<postgres_user>          # must match backend/.env.migrate.production's DATABASE_URL_BOOTSTRAP_SYNC
POSTGRES_PASSWORD=<postgres_password>  # must match backend/.env.migrate.production's DATABASE_URL_BOOTSTRAP_SYNC
POSTGRES_DB=<db>
NEXT_PUBLIC_API_URL=https://your-public-domain   # NO /api suffix — see §5 pitfall
HTTP_PORT=80
```

`docker compose` fails fast with a clear error (`POSTGRES_USER is required`)
if these aren't set, rather than silently booting with a blank password.

`POSTGRES_USER`/`POSTGRES_PASSWORD` are the Postgres image's bootstrap
superuser — required by the official image, but never used by `api` or
`worker` after the one-off `migrate` step below creates and grants the two
restricted roles those services actually connect as (`erp_migrate`,
`erp_app`). No standing superuser credential is used at runtime.

## 4. Deploy steps

```bash
cd infra

# 1. Build all images
docker compose -f docker-compose.prod.yml build

# 2. Bring up the database and cache first, wait for health
docker compose -f docker-compose.prod.yml up -d postgres redis

# 3. Bootstrap the erp_migrate/erp_app roles (idempotent) and run
#    migrations — a deliberate, reviewed one-off step, not part of `up`.
#    See 17c-rls-runtime-role-hardening.md for what this actually does.
docker compose -f docker-compose.prod.yml run --rm migrate

# 4. Bring up everything else
docker compose -f docker-compose.prod.yml up -d api worker frontend nginx

# 5. Verify
curl http://localhost/api/v1/identity/bootstrap -X OPTIONS   # should not 404
docker compose -f docker-compose.prod.yml ps                  # all healthy
```

**Subsequent deploys** (code already in a new image): repeat steps 1, 3
(if there are new migrations), then `up -d` again — compose recreates only
the containers whose image actually changed.

**Rollback**: `docker compose -f docker-compose.prod.yml up -d <service>`
against a previously-tagged image; database migrations in this nucleus are
additive-only so far (no destructive `downgrade` paths have been needed) —
a real rollback plan needs per-migration `downgrade()` review before this
matters in practice.

## 5. Pitfall this phase actually hit (and fixed)

`NEXT_PUBLIC_API_URL` must be the **origin only** — `http://localhost:8080`,
not `http://localhost:8080/api`. The frontend's `lib/api-client.ts` already
prepends the full `/api/v1/...` path to every request
(`fetch(`${API_BASE_URL}${path}`)` where `path` is e.g.
`/api/v1/identity/bootstrap`); setting the env var with an `/api` suffix
doubles it to `/api/api/v1/...` and every request 404s. This was caught
during verification (a bootstrap call failed, traced to the built JS bundle
via `grep` inside the frontend container), not left for a user to discover.
Because `NEXT_PUBLIC_*` vars are baked into the client bundle at **build**
time, fixing this requires rebuilding the frontend image, not just editing
`infra/.env` and restarting the container.

## 6. Health checks

- `GET /health` on the API container (used by its own Docker healthcheck) —
  reports Postgres connectivity, not just process liveness.
- `pg_isready` / `redis-cli ping` for the data tier.
- No dedicated frontend healthcheck yet — Next.js's standalone server has no
  built-in health route; `docker compose ps` shows it as running but not
  "healthy" (this is a known gap, not a bug).

## 7. Deferred (out of scope for this phase)

- Actual cloud provisioning / IaC (Terraform, cloud-specific load balancer,
  managed Postgres) — the containers are portable per NFR-PORT-001, but no
  cloud target was specified to provision against.
- TLS termination — nginx here is HTTP-only; a real deployment needs a
  cert (Let's Encrypt via certbot, or terminate TLS at a cloud load balancer
  in front of this stack).
- Celery Beat / scheduled jobs — nothing in the nucleus is periodic yet.
- Read replica, S3 for attachments — both explicitly optional-at-launch in
  the architecture doc.
- CI/CD pipeline (automated build-test-deploy on push) — this phase produced
  the deployable artifacts; wiring them into a pipeline is a natural
  Phase 15/follow-up item once a CI provider is chosen.
