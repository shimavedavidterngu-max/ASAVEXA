# ASAVEXA — Deployment Checklist

Each item is marked with its actual, current status in *this* sandbox, not
an assumption. "☐ Pending (env-blocked)" means the step cannot be completed
here specifically because of the network restriction documented in
`RUNTIME_REQUIREMENTS.md` — not because of any application defect.

## Pre-deployment

- [x] Repository available — `/home/claude/asavexa`, 445-test baseline green
- [ ] Dependencies available — **Pending (env-blocked).** `fastapi`, `sqlalchemy`,
      `psycopg`, `alembic`, `email-validator` cannot be installed (pip/apt
      both return 403 from every mirror). `uvicorn`, `pydantic`, `httpx`,
      `python-dotenv`, `python-multipart` already happen to be present.
- [x] Environment variables configured — `.env.example` documents both real
      variables (`DATABASE_URL`, `CORS_ALLOWED_ORIGINS`) with every
      conventional section present, unused ones explicitly marked N/A
- [x] Secrets configured (dev defaults) — `asavexa`/`asavexa` per
      `docker-compose.yml`; not suitable beyond local dev (see Step 13 notes
      in `RUNTIME_ENVIRONMENT_SPEC.md`)
- [x] Docker available — daemon starts and runs correctly (`docker info`
      succeeds); **image pulls are blocked**, see below
- [x] PostgreSQL available — **as a native (non-container) install**: real
      PostgreSQL 16.13 server started, connected, schema applied, verified
      (Phase 9). The `postgres:16` **container image** itself was never
      pulled or run.

## Deployment

- [ ] Images built — **NOT EXECUTED.** `docker compose build` fails at the
      first step for both the `api` and `frontend` services:
      `failed to resolve source metadata for docker.io/library/nginx:alpine:
      ... Forbidden` and the same for `python:3.12-slim`. Reason:
      environment limitation (Docker Hub unreachable), not a Dockerfile
      defect — `docker compose config` (static validation) passes with zero
      errors.
- [x] Database started — real, via the native (non-container) PostgreSQL
      16 install, not via `docker compose up db`
- [x] Migrations executed — **by direct equivalent, not by `alembic`
      itself**: `alembic upgrade head` cannot run (no `alembic` package),
      but the migration file it would run does nothing but
      `op.execute(open("schema.sql").read())` — that exact file was applied
      directly via `psql`, producing all 17 tables, 33 FKs, 162 CHECK
      constraints, 54 indexes with zero errors
- [ ] Backend started — **NOT EXECUTED.** `ModuleNotFoundError: No module
      named 'fastapi'` on direct import of `asavexa.api.main`; no install
      path available
- [x] Frontend started — real static file server (`python3 -m http.server`)
      served the actual, unmodified `frontend/index.html` + `src/`
- [ ] nginx started — **NOT EXECUTED.** nginx is not installed in this
      sandbox and cannot be installed (apt blocked); the frontend was
      instead served directly for verification purposes, which bypasses
      nginx's reverse-proxy and security-header behavior entirely

## Verification

- [ ] Health endpoint — **NOT EXECUTED** (backend not running)
- [ ] Readiness endpoint — **NOT EXECUTED** (backend not running)
- [x] Database connectivity — **verified**, real connection as the
      application's own `asavexa` role against a real `asavexa` database
- [ ] Authentication — **NOT EXECUTED** (backend not running)
- [ ] Authorization — **NOT EXECUTED** (backend not running); the
      permission *matrix* itself is exhaustively unit-tested (both backend
      domain layer and frontend), but no live HTTP authorization decision
      was made
- [ ] Tenant isolation — **NOT EXECUTED** as a live cross-org HTTP test;
      unit-tested at the domain layer only
- [ ] Accounting (live workflow) — **NOT EXECUTED**
- [ ] Evidence Vault (live workflow) — **NOT EXECUTED**
- [ ] Reconciliation (live workflow) — **NOT EXECUTED**
- [ ] Reporting (live workflow) — **NOT EXECUTED**
- [ ] Period Close (live workflow) — **NOT EXECUTED**
- [ ] Controls (live workflow) — **NOT EXECUTED**
- [ ] Administration (live workflow) — **NOT EXECUTED**
- [ ] Audit Workspace (live workflow) — **NOT EXECUTED**
- [x] Browser workflow (partial) — real Chromium (Playwright) loaded the
      real, unmodified frontend statically served; real DOM render of the
      Login screen, zero JavaScript page errors. **Not** tested: any
      authenticated workflow, since there is no live API for it to call.

## Recovery

- [x] Logs — documented location: `/var/log/postgresql/postgresql-16-main.log`
      (native Postgres) and stdout/stderr for the API container (per its
      unconditional stdlib `logging` setup in `api/main.py`); no separate
      log-shipping mechanism exists in the repo, none invented here
- [x] Database backup — documented, not exercised: `pg_dump` against the
      `asavexa` database (standard PostgreSQL tooling, no custom backup
      script exists in the repo)
- [x] Rollback — documented: `alembic downgrade -1` is implemented in the
      one existing migration (`migrations/versions/9ab0a651f090_initial_schema.py`'s
      `downgrade()`, which drops all 17 tables in reverse dependency order)
      — not executed here since `alembic` itself is unavailable
- [x] Restart procedure — documented: `docker compose restart <service>`
      per the compose file's `restart: unless-stopped` policy already set
      on every service; native-Postgres equivalent used here was
      `service postgresql start`/`pg_ctlcluster`

---

**Overall deployment status: NOT deployed.** Every unchecked item above is
blocked specifically by this sandbox's network restriction (no path to
PyPI, npm, Docker Hub, or Ubuntu archive mirrors — three independent
channels, each confirmed with a single real attempt, not repeatedly
retried), not by any defect discovered in the application, its Dockerfiles,
or its Compose configuration. See `RUNTIME_ENVIRONMENT_SPEC.md` for exactly
what an external, network-enabled environment needs to provide to complete
every remaining item.
