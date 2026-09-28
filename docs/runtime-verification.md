# ASAVEXA — Runtime Verification Status

This document exists because a category of verification genuinely cannot be
performed in the sandbox this codebase was developed in — no network access,
no cached wheels for `fastapi`, `sqlalchemy`, `pydantic`, `uvicorn`, or
`psycopg` anywhere on the filesystem (verified directly by searching the
filesystem and attempting `pip install`, not assumed). This is a hard,
categorical constraint of that one environment, not a reflection of the
application's own readiness. This document draws an explicit line between
what has actually been executed and what has not, and gives the exact
procedure to close that gap in any environment where the dependencies can
be installed.

**Reconfirmed at Phase 6 via a third, independent channel.** Beyond `pip`
and `npm` (both already documented as blocked), Phase 6 also attempted a
real (non-dry-run) `apt-get install postgresql` — Ubuntu's own system
package manager, a completely different mechanism from either language's
package registry. DNS resolution to the Ubuntu mirrors succeeded, but every
actual package download returned `403 Forbidden` (`x-deny-reason:
host_not_allowed`), the same egress-proxy allowlist behavior blocking pip
and npm. This confirms — via pip, npm, *and* apt, three independent
package-management systems — that no new software of any kind can be
installed in this sandbox, by any mechanism. PostgreSQL itself cannot be
installed here either, not just the Python/Node clients for it.

**No fake framework was built to paper over this gap.** Nothing in this
repository defines a module named `fastapi`, `sqlalchemy`, `pydantic`,
`starlette`, or `psycopg`. Every check described below either (a) executes
real, framework-independent Python against the real domain/service/
repository layer, or (b) statically parses the real API source with
Python's `ast` module and cross-checks it against real, imported classes —
neither of which requires or pretends to be the frameworks themselves.

---

## Verified in the current environment (executed, not assumed)

- **Domain tests** — 198 tests across 7 modules (`accounting`, `identity`,
  `evidence`, `reconciliation`, `reporting`, `period_close`, `compliance`),
  stdlib-only, against real SQLite-backed repositories.
- **Cross-module integration tests** — maker/checker separation, tenant
  isolation, and audit-trail integrity proven with real actors across
  module boundaries (5 dedicated integration test files).
- **SQLite repository/service tests** — every domain operation exercised
  against a real (in-memory) SQLite database via the stdlib `sqlite3`
  module — real SQL, real transactions, real constraint enforcement.
- **API boundary contract tests** (`tests/test_api_boundary_contracts.py`,
  13 tests) — genuine, executable verification of the API layer's own
  logic, distinct from the frameworks underneath it:
  - Every exception class `api/main.py` classifies into an HTTP-status
    bucket is a real, correctly-subclassed, unambiguously-routed member
    of that bucket (checked with real `issubclass()` against real,
    imported domain error classes).
  - Every router→service call site (170+ checked) references a real
    method with real keyword-argument names on the actual service class
    (checked with real `inspect.signature()`).
  - Every router named in `api/main.py`'s `include_router(...)` calls is
    defined exactly once, with a coherent, non-overlapping URL prefix.
  - Every `require_permission(X)` call site (40+ checked) references a
    real, defined permission constant.
  - The specific domain-level facts a few router error paths depend on
    (e.g. "a missing journal id resolves to `None`, not an exception")
    are proven to actually hold.
  - `api/db/base.py`'s engine construction is proven lazy (never called
    at module import time) by direct AST inspection.
  - All 16 SQLite/SQLAlchemy repository pairs have full method-name and
    parameter-name parity (checked by combining real `inspect.signature`
    on the SQLite classes with static AST parsing of the SQLAlchemy
    classes — found and fixed one real, if currently benign, mismatch:
    `SqlAlchemySessionRepository.create`/`.update` used parameter name
    `session_` instead of `session`).
- **Static cross-reference check** (`audit_tools/static_check.py`) — all
  303 relative imports across all 39 files in `api/` resolve to a real
  name or submodule (zero dangling references).

## Not verified in the current environment

- Actual FastAPI application startup (`uvicorn asavexa.api.main:app`)
- Actual Starlette routing / request dispatch
- Actual Pydantic runtime request validation and response serialization
- Actual SQLAlchemy engine behavior against a real database connection
- Actual psycopg PostgreSQL driver behavior
- Actual HTTP request/response execution of any kind (status codes,
  headers, body encoding) — the API boundary contract tests above prove
  the application's *own* logic is internally consistent; they do not
  and cannot prove the frameworks correctly dispatch to it
- File upload handling (`UploadFile`/`File`/`Form` — used by the evidence
  router) under real multipart parsing
- Real database migration execution (no Alembic migrations exist yet —
  `schema.sql` is hand-written DDL, never applied to a live PostgreSQL
  instance in this environment)
- Connection pooling, transaction rollback-on-error, and concurrent-
  request behavior under a real ASGI server

## Required external runtime environment

Exact dependencies and lower-bound versions, taken directly from
`requirements.txt` (not invented — that file states these are lower
bounds, written without live internet access, and should be checked
against current releases before installing):

```
fastapi>=0.110
uvicorn[standard]>=0.29
sqlalchemy>=2.0
psycopg[binary]>=3.1
pydantic>=2.6
email-validator>=2.1     # required for pydantic's EmailStr (auth schemas)
python-multipart>=0.0.9  # required for FastAPI file uploads (evidence router)
alembic>=1.13
python-dotenv>=1.0

# For running the API test suite once the above are installed:
pytest>=8.0
httpx>=0.27
```

Plus a running PostgreSQL instance reachable at the `DATABASE_URL`
configured in `.env` (see `.env.example`).

## Recommended: Docker Compose (simplest path, added in Phase 6)

`docker-compose.yml`, `Dockerfile`, and `frontend/nginx.conf` (all new in
Phase 6) define the complete stack — PostgreSQL, the API, and the static
frontend reverse-proxied through nginx so no CORS configuration is even
needed for this path. Not executed here (`docker compose up` would need
to pull base images over the network this sandbox blocks — see above),
but written to be correct and runnable as-is once network access exists:

```bash
docker compose up --build
# Frontend:  http://localhost:8080
# API:       http://localhost:8000  (curl http://localhost:8000/ready)
```

This one command replaces the manual venv/install/migrate/serve sequence
below for anyone who has Docker — the manual path remains documented for
environments without it.

## Exact commands to run genuine verification (without Docker)

In an environment with network access:

```bash
cd asavexa

# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure the database
cp .env.example .env
# edit .env — set DATABASE_URL to a real, reachable PostgreSQL instance

# 3. Apply the schema via Alembic (added in Phase 3 — reads
#    schema.sql's live content, so this and schema.sql can never
#    silently diverge; see docs/postgresql-runtime-verification.md)
alembic upgrade head

# 4. Confirm the domain suite still passes unchanged (this part works
#    in any environment, dependencies or not)
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 5. Start the real application
PYTHONPATH=src uvicorn asavexa.api.main:app --reload

# 6. In another shell, confirm it's actually alive
curl http://localhost:8000/health
# expect: {"status":"ok","modules":["identity","accounting","evidence",
#          "reconciliation","reporting","period_close","compliance"]}

# 7. Exercise the real acceptance flow (once written — see Phase 11)
#    against the real running server, e.g. with httpx or pytest+httpx,
#    hitting real HTTP endpoints with a real ASGI transport.
```

At that point — and only at that point — the items listed under "Not
verified" above can be moved to "Verified," because they will have
actually executed against the real frameworks.

## What would immediately regress if this document's boundary were ignored

If a future change imports `fastapi`/`sqlalchemy` directly inside a
domain/service/repository module (rather than only inside `api/`), the
198 domain tests would stop being runnable without those packages
installed — which is precisely the property that has let this codebase
be tested at every stage of its development in a network-restricted
sandbox. Keeping the framework boundary at exactly the `api/` package
is not a stylistic preference; it is what made 213 tests executable
here at all.
