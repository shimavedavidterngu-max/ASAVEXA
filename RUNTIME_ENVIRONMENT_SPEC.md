# ASAVEXA — External Runtime Environment Specification

Exact specification for a machine/environment that can execute Phase 9's
genuine PostgreSQL + FastAPI + frontend/browser end-to-end verification.
Resource figures are based on what this sandbox actually used, not invented
headroom.

## Operating system

Linux (this repo's Dockerfiles target Debian-based `python:3.12-slim` and
Alpine-based `nginx:alpine`); any modern Linux distribution with Docker
support works as the host. Verified in this sandbox on Ubuntu 24.04 (noble),
kernel 6.18.

## CPU

No minimum stated anywhere in the repo. This sandbox's single vCPU ran the
full 445-test suite (277 backend + 168 frontend) in ~40 seconds combined and
built a real PostgreSQL schema in under a second — 1 vCPU is sufficient for
development/verification; not a production sizing recommendation, which the
repo makes no claim about either.

## RAM

This sandbox observed 7.8 GiB total (`docker info`'s "Total Memory"); the
actual application (native PostgreSQL 16 + the intended FastAPI process) is
lightweight — no figure in the repo suggests more is required for
verification purposes.

## Disk

Enough for: three Docker images (`python:3.12-slim`, `postgres:16`,
`nginx:alpine` — combined typically well under 1 GB compressed), the
Postgres data volume (empty schema is negligible), and this repo (~a few MB).
No large datasets are part of this project.

## Python

`3.12` (matches `Dockerfile`'s `FROM python:3.12-slim`). This sandbox has
`3.11.15` installed instead — close but not the pinned version; not
identical, and this difference is called out rather than glossed over.

## Node.js

Not required to run the application (zero npm dependencies, no build step).
Only needed, at any version, to run the frontend's own `node --test` suite
during development. This sandbox has v22.22.2.

## npm

Not required at all by this application.

## Docker

Any recent version with BuildKit support (this sandbox has 29.4.3 — daemon
starts and runs correctly here; the blocker is registry access, not the
Docker installation itself).

## Docker Compose

Any version supporting the Compose v2 schema used in `docker-compose.yml`
(healthcheck `condition: service_healthy`, named volumes). This sandbox has
v5.1.3 and successfully statically validates the file (`docker compose
config` succeeds with zero errors).

## PostgreSQL

Version `16` (exact tag pinned in `docker-compose.yml`: `image: postgres:16`).
This sandbox's natively-installed `postgresql-16` (16.13) was used as a
verified stand-in in Phase 9 and reproduced the real schema/transaction
behavior correctly — but the **containerized** `postgres:16` image itself was
never pulled or run here, since Docker Hub is unreachable.

## Browser

Any browser with native ES module support for manual use. For automated
verification, Chromium (this sandbox already has a working pre-installed
build at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`, driven
successfully via Playwright in Phase 9 — real page load, zero JS errors).

## Network access

The single hard requirement this sandbox lacks. The external environment
must be able to reach, at minimum:

| Host | For |
|---|---|
| `pypi.org`, `files.pythonhosted.org` | `pip install -r requirements.txt` |
| `registry-1.docker.io` (Docker Hub) | pulling `python:3.12-slim`, `postgres:16`, `nginx:alpine` |
| Optionally `archive.ubuntu.com` | only if not using the Docker path and installing `apt` packages directly on a bare host |

No other external host is required anywhere in the codebase (no third-party
API calls, no license servers, no telemetry endpoints).

## Required ports

`5432` (Postgres, internal Docker network only — never published to the
host, by explicit design decision documented in `docker-compose.yml`),
`8000` (API, published), `8080` (frontend, published, mapped to nginx's
internal `80`).

## Required credentials

Exactly what `docker-compose.yml` already sets for local/dev use:
`POSTGRES_USER=asavexa`, `POSTGRES_PASSWORD=asavexa`, `POSTGRES_DB=asavexa`.
No API secret key, no JWT signing secret, no third-party API key exists
anywhere in this codebase (auth is opaque server-side session tokens, not
signed tokens — see `.env.example`'s "Authentication" section). For any
deployment beyond local dev, the Postgres password should be replaced with a
real secret injected via the deployment platform's own secret store — never
committed to the repo (see Step 13 in the Phase 10 report below).

## Required environment variables

`DATABASE_URL`, `CORS_ALLOWED_ORIGINS` — the complete list; see
`.env.example` for the full, section-organized reference with every other
conventional section (Storage, Frontend, nginx, Observability) explicitly
marked not-applicable rather than omitted.

## Required dependency caches

None exist in this repo today. For a genuinely offline-capable provisioning
path, an external network-enabled machine would need to produce and transfer
in:
- A local Python wheel cache for everything in `requirements.txt` (e.g. via
  `pip download -r requirements.txt -d wheelhouse/`)
- The three Docker images saved to tarballs (`docker save python:3.12-slim
  postgres:16 nginx:alpine -o asavexa-base-images.tar`)
- No npm cache is needed (zero npm dependencies)
- No browser download is needed if the target sandbox already has a
  pre-installed Chromium, as this one does

## Required commands

```bash
git clone <repo-url> asavexa && cd asavexa
cp .env.example .env
docker compose build
docker compose up
curl http://localhost:8000/health
curl http://localhost:8000/ready
open http://localhost:8080
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test frontend/tests/*.test.js
```

None of these commands have been confirmed to succeed end-to-end in this
sandbox. `docker compose config` (static validation) succeeds. `docker
compose build` fails at the first base-image pull (`nginx:alpine` /
`python:3.12-slim` — `403 Forbidden`) — see the Phase 10 report for the
literal error output.
