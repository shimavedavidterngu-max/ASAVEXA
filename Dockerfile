# ASAVEXA API — production/dev container image.
#
# NOT built or executed in the sandbox that produced this codebase —
# `docker build` requires pulling the base image and pip-installing
# requirements.txt, both of which need network access this sandbox's
# egress proxy blocks (confirmed directly across three independent
# channels — pip, npm, and a real apt-get install — all returning 403
# Forbidden; see docs/runtime-verification.md and the Phase 6/7
# reports). Written to be correct and buildable in any environment
# with real network access. STATICALLY VERIFIED here (syntax, layer
# ordering, non-root execution, health check presence) — never
# claimed as RUNTIME VERIFIED; see docs/DEPLOYMENT.md's readiness
# matrix for the exact distinction.
FROM python:3.12-slim AS base

WORKDIR /app

# System deps for psycopg[binary] are usually unnecessary (it ships
# its own libpq), but libpq-dev covers the rare case a wheel isn't
# available for the target platform and it needs to compile.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY schema.sql alembic.ini ./
COPY scripts/ ./scripts/
COPY migrations/ ./migrations/

# Non-root execution (Phase 7, Step 3 — found missing during this
# audit: the image previously ran as root with no USER directive at
# all). The app only ever needs to read its own files and talk to the
# database over the network — no reason to run as root at any point
# after the build's own apt-get/pip steps, which still run as root
# (the default) since only root can install system/site packages.
RUN useradd --system --no-create-home --uid 10001 asavexa \
    && chown -R asavexa:asavexa /app
USER asavexa

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Container-level health check (Phase 7, Step 3 — found missing: only
# the compose file's *database* service had one). Uses Python's own
# stdlib rather than installing curl, keeping the image minimal. Hits
# /health (liveness), not /ready, matching Docker's own HEALTHCHECK
# semantics: Docker restarts a container it considers unhealthy, which
# should never happen merely because the database is briefly
# unreachable (that is what /ready — checked separately by whatever
# orchestrates traffic routing — is for; see api/main.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"]

# Applies migrations, then starts the real server. In production,
# split these into separate deploy steps (run migrations once, then
# roll out the new app image) rather than doing both on every
# container start — kept together here for a single, simple
# `docker-compose up` developer experience.
CMD ["sh", "-c", "alembic upgrade head && uvicorn asavexa.api.main:app --host 0.0.0.0 --port 8000"]

