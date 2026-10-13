# Stage 1: database migrations, backup plan and rollback

Status words used here: **VERIFIED IN TEST ENVIRONMENT** means it ran on a throwaway PostgreSQL 16 (never on your production database). Nothing in this document is **VERIFIED IN PRODUCTION**.

## 1. What changed
- The application used to create six tables itself every time it started (`organisation_profiles`, `organisation_standards`, `organisation_structures`, `passport_shares`, `passport_share_sessions`, `security_docs`), and only logged a message if that failed.
- Those tables now come from a tracked Alembic revision, **`b7c1d2e3f4a5`** (`migrations/versions/b7c1d2e3f4a5_late_tables.py`, SQL in `migrations/sql/`). The application **no longer creates tables**. At start-up it only checks that all 23 tables exist (`src/asavexa/api/schema_check.py`).
- Revision chain: `9ab0a651f090` (the 17 tables from `schema.sql`) → `b7c1d2e3f4a5` (the six). One head.
- The cumulative schema is therefore **`schema.sql` + `migrations/sql/*.up.sql`**. `schema.sql` was deliberately not edited, so the first revision stays a faithful copy.

## 2. Why this cannot damage existing data
- `upgrade` contains only `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`. No `ALTER`, `DROP`, `DELETE`, `UPDATE` or `INSERT` (a test fails the build if one is added).
- Production already has the six tables (the old start-up code made them). On those, the migration does nothing and touches no row.
- Proven on real PostgreSQL 16 (see `tests/test_stage1_migrations.py`, 4 tests): a fresh database; a production-like database with rows in `organisation_profiles`, `security_docs` and `passport_shares` (checksums identical before and after, run twice); a database where the migration was never run (the start-up check names the missing tables).
- In CI, `scripts/schema_parity.py` also builds the tables the *old way* (SQLAlchemy models) and compares columns, indexes and constraints with the migrated database. That comparison needs SQLAlchemy, which this sandbox cannot install, so it is **IMPLEMENTED, NOT YET RUN**.

## 3. Start-up check (`ASAVEXA_SCHEMA_CHECK`)
| Value | Behaviour |
|---|---|
| `strict` (default) | A missing table is logged at CRITICAL level, naming the table and `alembic upgrade head`, and the server **refuses to start**. |
| `warn` | Same log line, server starts anyway. Use only as a temporary emergency measure. |
A database that cannot be reached is not treated as a schema failure (`/ready` reports that); start-up carries on.

## 4. Before you deploy: read-only preflight (production)
Do **not** guess the production setup. Check it, in this order. Nothing below changes data.

1. **Render dashboard, backend service, Settings.** Note whether the service is Docker or native Python, and its *Start Command*. The Docker image runs `alembic upgrade head && uvicorn …`. If your service uses a different start command, tell me what it says. (Do not paste any value from the Environment tab.)
2. **Environment tab.** Confirm `DATABASE_URL` exists and starts with `postgres`. Do not copy it anywhere.
3. **Render Shell** (service → Shell), then run `python scripts/db_preflight.py`. It opens a read-only transaction, never prints the URL, and ends with a **verdict** line. Paste me only that output.
4. **Backup first.** In the Render dashboard open your PostgreSQL database and look at *Backups* / *Recovery* (what is offered depends on your plan, so check rather than assume). Take a manual backup or export, and note its time. If your plan has no backups, say so and we will make a `pg_dump` copy before anything is deployed.

Decision table from the preflight verdict:
| Verdict | Meaning | Action |
|---|---|---|
| At initial revision | Normal for production | Deploy; the migration adds revision `b7c1d2e3f4a5` safely |
| Already at latest | Migration already applied | Nothing to migrate |
| Tables exist but **no alembic_version** | Alembic never ran there (tables made another way) | **Stop.** After the backup, run `alembic stamp 9ab0a651f090` once, then upgrade. Deploying without this would fail, because Alembic would try to create tables that exist |
| Base tables missing / unknown revision | Unexpected | **Stop** and send me the verdict line |

## 5. Backup and rollback plan
**Principle:** the change is additive, so the usual rollback needs no database action.

| Situation | Rollback |
|---|---|
| The new code misbehaves, database fine | Redeploy the previous commit (`2058ad9`, and the tag `stage0-baseline` if you created it). The six tables simply stay, unused by nothing: the old code's start-up step finds them already there. **No data change.** |
| The migration step fails part-way | Each statement is independent and idempotent; fix the cause and run `alembic upgrade head` again. Nothing is half-applied in a way that blocks a re-run |
| Data damaged by something else | Restore the backup taken in step 4 (Render restore, or `pg_restore`). Restore drill below shows the procedure works |
| You really need to remove the six tables | `ASAVEXA_ALLOW_DESTRUCTIVE_DOWNGRADE=1 alembic downgrade 9ab0a651f090`. **This deletes real data** (MFA state, audit-chain links, passport shares, profiles). The command refuses to run without that variable. Take and verify a backup first. Never do this on production without a separate review |

**Restore drill (VERIFIED IN TEST ENVIRONMENT, 2026-10-12, PostgreSQL 16, throwaway database):** `pg_dump -Fc` of a migrated database holding rows in `organisations`, `organisation_profiles`, `security_docs` and `passport_shares` → new empty database → `pg_restore`. Row counts (2 / 1 / 2 / 1) and content checksums were identical in source and restored copy; 23 tables. The application's own backup module also passed its 3 PostgreSQL tests (backup, integrity verification, restore round-trip, tamper detection).
The same drill has **not** been done against Render's PostgreSQL. Do it once, into a *new scratch database*, never over production.

## 6. Commands
| Purpose | Command |
|---|---|
| Apply migrations | `alembic upgrade head` |
| Show where a database is | `alembic current` |
| Offline SQL (review only) | `alembic upgrade head --sql` |
| Read-only production preflight | `python scripts/db_preflight.py` |
| Check migrated schema equals the ORM-created one (CI) | `python scripts/schema_parity.py` |

## 7. Honest limits
- Alembic itself (`env.py`, the revision file) could not run in the development sandbox (no SQLAlchemy/Alembic/psycopg available). The revision's logic is unit-tested with a stand-in `op`, and its SQL is proven on PostgreSQL through `psql`. The first real `alembic upgrade head` happens in GitHub Actions.
- No operation of any kind has been run against Render or the production database.
