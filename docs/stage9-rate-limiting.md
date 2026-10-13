# Stage 9: shared rate limiting

Status: **VERIFIED IN TEST ENVIRONMENT** (18 tests, including the exact SQL on real PostgreSQL 16). Alembic itself, real SQLAlchemy and a multi-instance deployment have not been run. Off by default.

## What changed
- New migration `c4d5e6f7a8b9` adds one table, `rate_limit_hits` (throttle key, window start, count). `CREATE ... IF NOT EXISTS` only; no existing table or row is touched. SQL in `migrations/sql/c4d5e6f7a8b9_rate_limit_hits.{up,down}.sql`.
- `security/sharedlimit.py`: a limiter with the same interface as the old one, counting in the database with one atomic upsert so several server instances count together.
- `api/ratelimit.py`: uses it only if `RATE_LIMIT_BACKEND=postgres`. Anything else keeps today's per-instance in-memory limiter, unchanged (a test asserts the defaults and limits are the same).

## Safety properties
- If the database or table is unavailable, it falls back to per-instance counting and logs a warning once a minute. A database problem never locks people out.
- Each hit commits on its own short connection, so a failed request cannot roll a hit back.
- The table is NOT in the start-up required-tables list: a deployment where the migration has not run still starts.
- Trade-off: fixed windows. A burst straddling a window edge can briefly allow up to twice the limit. The in-memory limiter was a sliding window.

## To turn it on (only when you run more than one server instance)
1. `python scripts/db_preflight.py` (read-only), take a backup, then `alembic upgrade head`.
2. Set `RATE_LIMIT_BACKEND=postgres` in the server environment and redeploy.
3. Check the log for "shared rate limiter unavailable"; it means it is counting per instance.
Rollback: unset the variable and redeploy. The table can stay.
