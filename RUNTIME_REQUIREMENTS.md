# ASAVEXA — Runtime Requirements Manifest

Every value below was read directly out of this repository (`requirements.txt`,
`Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `frontend/nginx.conf`,
`alembic.ini`, `.env.example`, `src/asavexa/api/main.py`) — nothing here is
invented or assumed. Where the repo gives a lower bound rather than an exact
pin, that is stated as such rather than presented as a fixed version.

---

## Required software

### Backend

| Requirement | Exact value from the repo | Source |
|---|---|---|
| Python | `3.12-slim` (container base image) | `Dockerfile` line `FROM python:3.12-slim AS base` |
| ASGI server | `uvicorn[standard]>=0.29` | `requirements.txt` |
| Web framework | `fastapi>=0.110` | `requirements.txt` |
| ORM | `sqlalchemy>=2.0` | `requirements.txt` |
| PostgreSQL driver | `psycopg[binary]>=3.1` (psycopg **3**, not psycopg2) | `requirements.txt` |
| Data validation | `pydantic>=2.6` | `requirements.txt` |
| Email validation | `email-validator>=2.1` (required for Pydantic's `EmailStr` in auth schemas) | `requirements.txt` |
| File uploads | `python-multipart>=0.0.9` (required for the evidence-upload router) | `requirements.txt` |
| Migration tool | `alembic>=1.13` | `requirements.txt` |
| Env loading | `python-dotenv>=1.0` | `requirements.txt` |
| Test runner (API layer) | `pytest>=8.0` (only for API-layer tests; the 277-test core suite uses only stdlib `unittest`) | `requirements.txt` |
| HTTP test client | `httpx>=0.27` | `requirements.txt` |
| Build-time system packages | `libpq-dev`, `gcc` (Debian packages, installed at image-build time only, in case a psycopg wheel isn't available for the target platform) | `Dockerfile` |

All version numbers above are **lower bounds** (`>=`), not exact pins — `requirements.txt` states explicitly it "has not been resolved/locked against real PyPI" since it was written without live internet access.

### Frontend

| Requirement | Exact value from the repo |
|---|---|
| Node.js | **None at runtime.** No `package.json` exists anywhere under `frontend/`. |
| npm | **None.** Zero npm dependencies by design — native ES modules only. |
| Build tooling | **None.** No bundler, no transpiler, no build step. |
| Browser requirement | Any browser with native ES module support (`<script type="module">`) |
| Browser automation (for verification, not for the app itself) | Playwright — already present in this sandbox at `/usr/local/lib/python3.11/dist-packages/playwright` and `/opt/node-tools/node_modules/playwright`, with Chromium pre-installed at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` |
| Node.js (dev-only) | Used only to run `node --test frontend/tests/*.test.js` during development — no version pin in the repo; this sandbox has v22.22.2 |

### Database

| Requirement | Exact value from the repo |
|---|---|
| PostgreSQL version | `postgres:16` (Docker image tag) — `docker-compose.yml` | 
| Extensions required | `gen_random_uuid()` is used as every table's PK default (`schema.sql`) — this is provided by PostgreSQL 13+'s built-in `pgcrypto`-free `gen_random_uuid()` (core since PG13); no `CREATE EXTENSION` statement appears anywhere in `schema.sql`, so no extension installation step is required beyond the base image |
| Database init | `POSTGRES_USER=asavexa`, `POSTGRES_PASSWORD=asavexa`, `POSTGRES_DB=asavexa` (`docker-compose.yml` environment block) |
| Migration requirement | `alembic upgrade head`, which executes `migrations/versions/9ab0a651f090_initial_schema.py`, which in turn applies `schema.sql` verbatim via `op.execute()` — there is deliberately no hand-transcribed Alembic DDL, `schema.sql` is the single source of truth |

### Infrastructure

| Requirement | Exact value from the repo |
|---|---|
| Docker | No version pinned in the repo; this sandbox has `29.4.3` |
| Docker Compose | No version pinned in the repo; this sandbox has `v5.1.3` |
| nginx | `nginx:alpine` (Docker image tag) — `frontend/Dockerfile` |
| Ports | `5432` (Postgres, **not** published to the host — internal Docker network only, by design, see `docker-compose.yml`'s own comment on this), `8000` (API, published), `8080→80` (frontend, published) |
| Environment variables | Exactly two used by application code: `DATABASE_URL`, `CORS_ALLOWED_ORIGINS` (confirmed by grepping `os.environ`/`os.getenv` across all of `src/asavexa/`) — see `.env.example` for the full, section-organized reference |

---

## Required images

| Image | Tag | Used by |
|---|---|---|
| `python` | `3.12-slim` | `Dockerfile` (api service base) |
| `postgres` | `16` | `docker-compose.yml` (db service) |
| `nginx` | `alpine` | `frontend/Dockerfile` (frontend service base) |

None of these three images are cached in this sandbox (`docker images` returns empty), and none can be pulled — see the Phase 9/10 network-capability findings below.

## Required network access

| Destination | Needed for | Reachable from this sandbox? |
|---|---|---|
| PyPI (`pypi.org`, `files.pythonhosted.org`) | `pip install -r requirements.txt` | **No — 403 Forbidden**, confirmed directly |
| npm registry (`registry.npmjs.org`) | Not required by this app at all (zero npm deps) — checked anyway for completeness | **No — 403 Forbidden** |
| Docker Hub (`registry-1.docker.io`) | Pulling `python:3.12-slim`, `postgres:16`, `nginx:alpine` | **No — 403 Forbidden**, confirmed via `docker pull` |
| Ubuntu archive mirrors (`archive.ubuntu.com`) | `apt-get install` of any package not already present | **No — 403 Forbidden**, confirmed via a real (non-simulated) `apt-get install` |

## Installation commands

As written in the repo, for an environment with real network access:

```bash
# Backend
pip install -r requirements.txt

# Database + API + frontend, all at once
docker compose build
docker compose up
```

## Startup commands

Exactly as declared in the repo (not invented):

```bash
# Backend (inside the container, or locally with DATABASE_URL set) — Dockerfile's own CMD:
alembic upgrade head && uvicorn asavexa.api.main:app --host 0.0.0.0 --port 8000

# Full stack:
docker compose up --build
```

## Verification commands

```bash
curl http://localhost:8000/health   # liveness — no DB touch (src/asavexa/api/main.py)
curl http://localhost:8000/ready    # readiness — real DB check via Depends(get_session)
open  http://localhost:8080         # frontend, reverse-proxied to the API at /api/*

# Test baseline
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test frontend/tests/*.test.js
```
