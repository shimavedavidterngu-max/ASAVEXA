# ASAVEXA — Deployment Guide

Companion to `docs/runtime-verification.md`, `docs/postgresql-runtime-verification.md`,
`docs/security-architecture.md`, and `docs/frontend-runtime-verification.md`.
Same honesty rule as all four: this sandbox cannot install or execute
PostgreSQL, FastAPI, SQLAlchemy, Docker, or npm packages — confirmed
directly across three independent channels (pip, npm, and a real
`apt-get install postgresql`, all returning `403 Forbidden`). Every
procedure below is **STATICALLY VERIFIED** (the configuration is
correct, internally consistent, and covered by 275+ automated tests
that check its structure) and **CONTAINER-READY** (written to build
and run correctly once real infrastructure access exists) — never
**RUNTIME VERIFIED** unless explicitly marked otherwise, which nothing
in this document is.

---

## 1. Prerequisites

- Docker + Docker Compose (recommended path — see §3), **or**
- Python 3.12+, PostgreSQL 16, and (for the frontend) any static file
  server — for a manual, non-Docker setup (see §4)
- Real network access to pull base images / install packages — this
  sandbox has none; see the note above

No other prerequisite exists. There is no separate build step for the
frontend (vanilla JS, native ES modules — see
`docs/frontend-runtime-verification.md`) and no Node.js requirement at
deployment time (only during this project's own development, for
`node --test`).

## 2. Environment variables

The application recognizes exactly two configuration variables — none
were added speculatively:

| Variable | Used by | Example | Required |
|---|---|---|---|
| `DATABASE_URL` | `api/db/base.py` | `postgresql+psycopg://asavexa:asavexa@localhost:5432/asavexa` | Yes (falls back to a local-dev default otherwise) |
| `CORS_ALLOWED_ORIGINS` | `api/main.py` | `https://app.example.com` | Recommended in any multi-origin deployment; falls back to local-dev origins otherwise |

Copy `.env.example` to `.env` and edit it — **never commit `.env`** (it
is not tracked; only `.env.example`, containing placeholders, is).
There is no application `SECRET_KEY`: session tokens are opaque,
random, database-backed values (SHA-256 hash of a `secrets.token_urlsafe(32)`
value), not JWT-signed — see `docs/security-architecture.md`.

**Environment separation** (development / testing / staging /
production) is achieved entirely by pointing `DATABASE_URL` and
`CORS_ALLOWED_ORIGINS` at the right values per environment — there is
deliberately no separate config *file* per environment (no
`.env.staging`, `.env.production` committed anywhere), since that would
risk one of them accidentally containing real values. Testing needs
neither variable at all: `PYTHONPATH=src python3 -m unittest discover
-s tests -v` runs entirely against in-memory SQLite, with zero
environment configuration.

## 3. Development / staging / production deployment (Docker Compose)

```bash
git clone <repository-url> && cd asavexa
cp .env.example .env   # edit if deploying beyond localhost
docker compose up --build
```

This one command builds and starts all three services (`db`, `api`,
`frontend`) per `docker-compose.yml`, applies migrations automatically
(the API container's `CMD` runs `alembic upgrade head` before starting
`uvicorn` — see `Dockerfile`), and serves the complete application at
`http://localhost:8080`.

The same compose file is appropriate for staging and production as a
starting point — differences between environments should be expressed
via environment variables (`DATABASE_URL` pointing at a managed
PostgreSQL instance, `CORS_ALLOWED_ORIGINS` set to the real production
origin) and, for production specifically, the two hardening items in
§15 below (a properly-scoped least-privilege database role, and a real
TLS-terminating layer in front of nginx) rather than a different
compose topology.

**CONTAINER-READY, not RUNTIME VERIFIED**: `docker compose up` has
never executed in the environment that produced this codebase.

## 4. Manual deployment (without Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set DATABASE_URL to a real, reachable PostgreSQL
alembic upgrade head
PYTHONPATH=src uvicorn asavexa.api.main:app --host 0.0.0.0 --port 8000

# in another shell, serve the frontend statically:
cd frontend && python3 -m http.server 8080
```

Without nginx's reverse proxy, the frontend and API are on different
origins — either set `CORS_ALLOWED_ORIGINS` to include the frontend's
origin, or change `frontend/src/api/client.js`'s `DEFAULT_BASE_URL`
to the API's full URL.

## 5. Database migrations

`alembic upgrade head` is the only supported schema-application path
(see `docs/postgresql-runtime-verification.md` for the full
architecture: the initial migration reads `schema.sql`'s live content
at migration-run time, so the two files can never silently diverge).

- **Fresh installation**: `alembic upgrade head` against an empty
  database creates every table from scratch.
- **Existing database**: `alembic upgrade head` again — Alembic tracks
  the applied revision in its own `alembic_version` table and is a
  no-op if already current.
- **Migration ordering**: linear, single-branch — verified by a
  regression test (`tests/test_database_schema_contracts.py`) that the
  one migration that exists has real `upgrade()`/`downgrade()`
  functions and its table list matches `schema.sql` exactly.
- **Failed migration**: Alembic runs each migration inside a database
  transaction by default; a failure rolls back that migration's own
  changes, but does **not** automatically retry or self-heal — an
  operator must diagnose and re-run `alembic upgrade head` after
  fixing the underlying issue.
- **Rollback**: `alembic downgrade base` drops every table (in reverse
  dependency order — see the migration file). This is inherently
  destructive (real data loss) and untested against a real database in
  this environment; take a real backup (§6) before ever running it
  against a database containing data you need.
- **Schema compatibility**: only one migration exists so far (the
  initial baseline). Future schema changes should be new migrations
  whose `upgrade()` contains only the incremental change, with
  `schema.sql` updated to match so it always reflects the cumulative
  current schema — never a second migration that silently re-embeds
  the whole schema again.

**No destructive migration behavior exists in the current migration
set** beyond the documented `downgrade()` (which is never run
automatically — only by explicit operator action).

## 6. Backup

**Documented procedure, not yet executed** (this sandbox has no
PostgreSQL to back up) — do not treat this as verified until a real
restore (§7) has actually succeeded once against a real backup file.

```bash
# Logical backup (recommended default — portable across PostgreSQL
# versions, human-inspectable, works with the docker-compose db service
# by name):
docker compose exec db pg_dump -U asavexa asavexa > backup-$(date +%Y%m%d-%H%M%S).sql

# Or, for a non-Docker deployment:
pg_dump -U asavexa -h <host> asavexa > backup-$(date +%Y%m%d-%H%M%S).sql
```

**Frequency recommendation**: daily, at minimum, for any deployment
holding real financial data — this is a recommendation, not something
this codebase enforces or schedules; wiring it to an actual cron job /
managed-database automated-backup feature is an infrastructure
decision for the real deployment target, intentionally not hard-coded
here.

**Retention recommendation**: 30 daily backups + 12 monthly backups is
a reasonable starting point for a financial-audit system, subject to
whatever regulatory retention requirements apply to the deploying
organisation — this codebase does not have visibility into those
requirements and does not choose a number on its own authority.

**Encryption**: `pg_dump`'s output is plain SQL text containing real
financial data — encrypt the backup file at rest (e.g. `gpg --encrypt`
or your object storage's server-side encryption) and in transit if
shipped off-host. Never commit a backup file to source control.

**Evidence storage backup**: separate from the database backup above —
see `docs/postgresql-runtime-verification.md`'s "Evidence persistence"
section: this codebase currently persists only evidence *metadata* in
PostgreSQL (covered by the backup above); the actual file content
storage mechanism is not yet implemented, so there is no evidence
*content* backup procedure to document yet — documented there as a
named future phase, not invented here.

**Configuration backup**: `.env` (never committed) should be backed up
separately, through whatever secrets-management mechanism the real
deployment uses (a secrets manager, an encrypted vault) — never
alongside the database backup, and never in the same access-control
scope as application data.

## 7. Restore

**Documented procedure, not yet executed.**

```bash
# Against a fresh, empty database:
alembic upgrade head          # recreate the schema
psql -U asavexa -h <host> asavexa < backup-20260101-020000.sql
```

**Recovery verification** (do this every time, not just the first
time): after restoring, run
`PYTHONPATH=src python3 -m unittest discover -s tests -v` against the
*application code* to confirm it still passes (proves the code and
schema are compatible), then separately query the restored database
directly to spot-check that expected data is actually present — an
`alembic upgrade head` that runs without error does not by itself
prove the restored *data* is correct, only that the *schema* is.

**Recovery dependencies**: a reachable PostgreSQL instance, the exact
backup file, and this repository's `alembic.ini`/`migrations/` at a
compatible version (a backup taken before a schema migration was
applied should be restored against the codebase version from before
that migration, then migrated forward with `alembic upgrade head` —
never restored directly against a newer schema).

**Do not consider disaster recovery operational until this exact
sequence has been executed once, for real, against a real backup
file** — nothing in this document claims that has happened.

## 8. Health checks

Two distinct endpoints, deliberately not conflated (Phase 3/Step 8):

- `GET /health` — **liveness**. No dependencies, always fast, never
  touches the database. "Is the process alive."
- `GET /ready` — **readiness**. Executes a real `SELECT 1` against the
  actual database session; returns `503` with the underlying error on
  failure. "Can this instance actually serve a real request."

Docker's own container-level `HEALTHCHECK` (added in `Dockerfile`
during this phase) targets `/health` specifically, not `/ready` — a
container must never be restarted merely because the database is
briefly unreachable, which is exactly the scenario `/ready` exists to
report separately (to whatever routes traffic, not to Docker's own
restart policy).

Neither endpoint exposes diagnostic detail beyond a boolean-shaped
status and (for `/ready`'s failure case) the raw database error message
— for a production deployment where even that level of detail is too
much to expose publicly, `/ready` should sit behind the same network
boundary as internal orchestration tooling, not the public internet.

## 9. Logs

Two genuinely distinct log stores — **never merge them**:

- **The shared audit trail** (`asavexa/audit/`, PostgreSQL-backed,
  append-only, no update/delete API anywhere in its interface —
  verified by direct source inspection). Business-meaning events: who
  posted which journal, who verified which finding. Queried by the
  application itself. Permanent.
- **Operational logs** (Python's stdlib `logging`, logger name
  `"asavexa"` — added during this phase; previously no logging
  infrastructure existed at all). Request-level events (method, path,
  status code, duration, a per-request `X-Request-ID`) and unhandled
  exceptions. Never queried by the application. Expected to roll
  over/expire per whatever log infrastructure the deployment provides
  (a container orchestrator's log driver, a log aggregation service) —
  this codebase does not configure log rotation or shipping itself.

**Never logged, anywhere, in either store** (verified by dedicated
regression tests, not just claimed): passwords, raw session tokens,
API keys, request bodies, or request headers. The request-logging
middleware specifically logs only method/path/status/duration/request-id
— confirmed by a test that statically checks it never reads
`request.body`, `request.headers`, `request.json`, or `request.form`.

## 10. Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| `/health` returns non-200 | Process genuinely not running/crashed | Container logs |
| `/ready` returns 503 | Database unreachable, wrong `DATABASE_URL`, migrations not applied | `/ready`'s response body has the real error; `alembic current` |
| CORS error in browser console | Frontend origin not in `CORS_ALLOWED_ORIGINS` | Confirm the exact origin (scheme+host+port) matches |
| 401 on every request | Session expired/revoked, or no `Authorization` header sent | Re-authenticate; confirm `Bearer <token>` header format |
| 403 on a specific action | Role genuinely lacks that permission (server-side enforced regardless of what the frontend shows) | `docs/security-architecture.md`'s permission matrix |
| 500 with a `request_id` | Unexpected server-side error (Phase 7's generic handler) | Search operational logs for that exact `request_id` |
| `nginx.conf` / `frontend/tests/*` fetchable from the browser | Deployed via a raw bind-mount instead of `frontend/Dockerfile`'s build (a real gap this phase fixed structurally) | Use `docker compose up --build`, never a manual bind-mount of the whole `frontend/` directory |

## 11. Security configuration

Full detail in `docs/security-architecture.md`; deployment-relevant
summary:

- **Authentication**: PBKDF2-HMAC-SHA256, 600,000 iterations (current
  OWASP recommendation, verified directly — not the previous, lower,
  incorrectly-labeled figure this project's own Phase 4 audit found
  and fixed). 15-character minimum password length (NIST SP 800-63B
  Rev. 4's single-factor floor — this application has no enforced MFA).
- **Sessions**: `secrets.token_urlsafe(32)`, SHA-256 hashed at rest,
  real expiration and revocation enforcement.
- **Authorization**: enforced exclusively server-side, at the API
  boundary, in every one of 7 domain modules — zero exceptions found
  across three separate audits (Phases 2, 4, 6).
- **Tenant isolation**: every repository query is `org_id`-scoped;
  cross-tenant access is indistinguishable from "not found," never
  leaking existence.
- **Database**: least-privilege role scoping is an **open item** — the
  current `docker-compose.yml` connects as a single role with full
  privileges on its own database. A production deployment should
  create a dedicated, narrower-privilege role for the application
  connection (see §15).
- **Infrastructure**: PostgreSQL is not published to the host network
  (fixed this phase — previously was); the API container runs as a
  non-root user (fixed this phase — previously ran as root); nginx
  denies its own config file and the `tests/` directory as
  defense-in-depth, though the frontend's own Dockerfile already
  prevents them from being present in the served image at all.
- **CORS**: environment-driven allowlist, never a wildcard,
  `allow_credentials=False` (matching the Bearer-token auth model —
  there is no cookie-based session for CORS credentials to protect,
  and therefore no CSRF surface from CORS itself).
- **Frontend**: confirmed by direct source sweep — zero secrets,
  API keys, or credentials anywhere in `frontend/src/`. The only
  configuration value the frontend needs (the API base URL) is not
  secret.
- **Evidence**: metadata-only persistence currently exists (content
  storage is a named future phase, not built or claimed here);
  metadata reads/writes go through the same tenant-isolated,
  permission-checked repository pattern as everything else.
- **Logging**: verified by regression test — no password, token, or
  request body/header content reaches either log store.

## 12. Rollback procedure

Application rollback: redeploy the previous container image/git
revision; if the schema didn't change between versions, no database
action is needed. If it did, `alembic downgrade` to the revision the
previous application version expects — **take a backup first (§6)**,
since downgrades can be destructive (dropping columns/tables), and
this has never been executed against a real database in this
environment. There is no automated rollback tooling in this
repository; this is a manual, operator-driven procedure.

## 13. Known runtime limitations

Unchanged in substance since Phase 2, reconfirmed via a third
independent channel in Phase 6 (a real `apt-get install postgresql`
attempt, blocked identically to pip and npm): **PostgreSQL, FastAPI,
SQLAlchemy, uvicorn, psycopg, alembic, Docker, and every npm package
remain uninstalled and unexecuted in the sandbox that produced this
codebase.** Every procedure in this document is statically verified
and container-ready, never runtime verified, until executed in an
environment with real network/infrastructure access. See §14 for the
exact readiness matrix.

## 14. Deployment readiness matrix

| Component | Static | Container-Ready | Runtime Tested | Status |
|---|:---:|:---:|:---:|---|
| Frontend | ✅ | ✅ | ❌ | 85 component tests pass; never rendered in a real browser |
| FastAPI | ✅ | ✅ | ❌ | 277 boundary-contract tests pass; process never started |
| PostgreSQL | ✅ | ✅ | ❌ | Schema/migration structure verified; no instance ever run |
| Migrations | ✅ | ✅ | ❌ | `alembic upgrade head` never executed for real |
| Authentication | ✅ | ✅ | ❌ | Full domain-layer test coverage; no real HTTP login ever performed |
| Authorization | ✅ | ✅ | ❌ | Enforced server-side in code, proven at the domain layer; never proven over real HTTP |
| nginx | ✅ | ✅ | ❌ | Config statically validated (13 tests); nginx binary never started |
| CORS | ✅ | ✅ | ❌ | Configuration validated (4 tests); no real cross-origin browser request ever made |
| Health checks | ✅ | ✅ | ❌ | Endpoint logic tested; never called over real HTTP |
| Logging | ✅ | N/A | ❌ | Call sites verified to exclude secrets; no real log output ever produced |
| Backup | ✅ (documented) | N/A | ❌ | Procedure written; `pg_dump` never run |
| Restore | ✅ (documented) | N/A | ❌ | Procedure written; never executed |
| E2E workflow | ❌ | N/A | ❌ | Requires a live stack; not attempted, per this phase's own instruction not to fabricate one |

## 15. Recommended next steps (before real production traffic)

1. Create a least-privilege PostgreSQL role for the application
   connection (currently a single full-privilege role) — a genuine,
   named open item, not fixed in this phase.
2. Put a real TLS-terminating layer in front of nginx (this repository
   configures HTTP only, appropriate for local/internal use; a real
   internet-facing deployment needs TLS, which is an infrastructure
   concern this repository does not attempt to solve on its own
   authority).
3. Execute this document's §3 (`docker compose up --build`) for real,
   for the first time, in an environment with network access — this is
   the single highest-value next action, since everything else in this
   document is downstream of it actually working.
