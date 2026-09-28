# ASAVEXA — PostgreSQL Runtime Verification & Persistence Architecture

Companion to `docs/runtime-verification.md` (the FastAPI/HTTP boundary), this
document covers the **production database and persistence architecture**
specifically: schema, migrations, transaction boundaries, tenant isolation,
and the exact procedure for real PostgreSQL verification once the required
packages are installable. Same honesty rule as its companion: nothing here
claims to have executed against a real PostgreSQL instance, because nothing
has — `alembic`, `sqlalchemy`, and `psycopg` are unavailable in this
sandbox (no network access, no cached wheels anywhere on the filesystem —
verified directly, not assumed).

---

## 1. Schema inventory — verified

All 17 persisted tables were cross-checked column-by-column across three
independent representations: `schema.sql` (PostgreSQL DDL), every SQLite
`CREATE TABLE` statement, and every SQLAlchemy ORM model. Automated,
regression-tested in `tests/test_database_schema_contracts.py`.

**Result: zero genuine schema defects.** Two apparent differences turned
out, on direct inspection, to be intentional and correct:

- `evidence_records.metadata` (DB column) vs `metadata_json` (ORM Python
  attribute) — SQLAlchemy's `DeclarativeBase` reserves the attribute name
  `metadata` for its own table registry, so the ORM class cannot have a
  column attribute literally named `metadata`; `mapped_column("metadata", ...)`
  is the standard, required pattern for this exact situation.
- SQLite names the accounting-periods table `periods`; `schema.sql` and the
  ORM name it `accounting_periods`. Confirmed cosmetic-only: no SQLite
  schema anywhere declares a `REFERENCES` foreign-key clause (tenant/
  business-rule enforcement for the SQLite test backend lives entirely at
  the service layer, not the database), so nothing anywhere references
  this table by name in a constraint. Left as-is rather than renamed, to
  avoid risk to the 200+ tests that depend on the current name, for a
  purely cosmetic gain.

## 2. `schema.sql`'s role — **Option A: supported bootstrap artifact**

`schema.sql` remains the single, canonical source of truth for the
production schema's DDL. It is not superseded by Alembic — it is *applied
by* Alembic. The initial migration (`migrations/versions/9ab0a651f090_initial_schema.py`)
does not reimplement the schema in Alembic's Python DSL; its `upgrade()`
reads and executes `schema.sql`'s actual file content at migration-run
time. There is exactly one place the schema's DDL is written down. Future
schema changes should be made by editing `schema.sql` and writing a new
migration whose `upgrade()` contains only the incremental `ALTER
TABLE`/`CREATE TABLE` statements for that change (with `schema.sql` updated
to match, so it always reflects the current, cumulative schema) — never by
letting a future migration and `schema.sql` describe different databases.

## 3. Migrations

Structure exists and is statically verified (`tests/test_database_schema_contracts.py::MigrationStructureTestCase`,
4 tests): `alembic.ini`, `migrations/env.py` (wired to the real ORM `Base`
and `DATABASE_URL`), `migrations/script.py.mako`, and one initial migration
whose `downgrade()` table list is checked to exactly match `schema.sql`'s
actual tables.

**One honest, unverified assumption**, stated in the migration's own
docstring: `upgrade()` passes `schema.sql`'s entire multi-statement content
to a single `op.execute()` call, relying on psycopg3 (this project pins
`psycopg[binary]>=3.1`, not psycopg2) supporting multi-statement execution
in one call — which it does, but this has not been run against a real
database here. If it doesn't behave as expected the first time it's run for
real, the fallback is splitting on statement-terminating `;` and calling
`op.execute()` per statement instead.

**Not verified**: actual `alembic upgrade head` execution against a live
PostgreSQL instance; actual `alembic downgrade` execution; Alembic's
version-tracking table (`alembic_version`) behavior.

## 4. Database initialization — fixed during this audit

`api/db/base.py` previously called `create_engine()` at module import time
(fixed in Phase 2: now lazy, via `get_engine()`/`get_session_factory()`,
proven never called at module top level via static AST inspection).

## 5. Transaction boundaries — **real defect found and fixed**

Every SQLAlchemy repository's `create()`/`update()` previously called
`self.session.commit()` independently (29 call sites across 7 files),
making every individual write its own auto-committed transaction with **no
atomicity across a multi-write service operation**. Concretely: `AccountingEngine.post_journal()`
updates the journal's status, then records an audit event, as two separate
repository calls — under the old behavior, if the audit-event write failed
after the journal-status write had already committed, the journal would be
left `POSTED` with no matching audit trail. The same risk existed across
every multi-write operation in this codebase: reversal, evidence
verification/rejection, reconciliation approval, period close, and every
finding/remediation transition.

**Fixed**: the transaction boundary now lives at the request level, in
`api/db/base.py::get_session()` — commits exactly once, after the request
handler completes without raising; rolls back on any exception. Individual
repository methods no longer call `commit()` at all (verified by a
regression test that fails if any of the 7 SQLAlchemy repository files
contains a `.commit()` call site).

This fix is **PostgreSQL/SQLAlchemy-layer-only**. The SQLite repositories
(used only for tests, never production) keep their existing per-operation
commit behavior — each SQLite `TestCase` uses a single shared in-memory
connection across the whole test, and the 231 existing tests' assumptions
are built around that. Changing it would touch every test file for a
backend that never serves real traffic; documented here as a deliberate
Category B (test-only) difference, not fixed to avoid unjustified risk.

## 6. Constraints and indexes — verified

Every tenant-scoped table this codebase's repositories actually query by
`org_id` has a matching index (or an equivalent `UNIQUE(org_id, ...)`
constraint, which PostgreSQL indexes implicitly) — checked against the 13
tenant-scoped tables and regression-tested
(`TenantIndexCoverageTestCase`). No index was added speculatively; each
one traces to a real query pattern already present in the repository
implementations (e.g. `idx_journals_org_status` backs
`journals.list_for_org(org_id, status=...)`, used by Period Close's and
Compliance's unposted-journal checks).

## 7. Tenant isolation at the database level — **decision: application-level filtering remains primary; no Row Level Security added**

Every read across every repository (SQLite and SQLAlchemy alike) filters
by `org_id` in its own query — verified exhaustively during the Phase 2
cross-module integrity audit (every `WHERE org_id=?` / `.where(...org_id
== org_id)` clause checked directly against source, not assumed) and
carried forward here for the PostgreSQL layer specifically: every
SQLAlchemy repository's `get`/`list_for_org` method includes `org_id` in
its `select(...).where(...)` call.

**Row Level Security was evaluated and deliberately not added.** Reasoning:
this architecture's tenant boundary is enforced consistently at exactly one
layer — the repository — across all seven modules, with a single,
well-tested pattern (`get(org_id, id)` returns `None` for a cross-tenant
id; every list method takes `org_id` as a required parameter). Introducing
RLS would add a *second*, database-level enforcement mechanism that the
application does not currently assume exists and is not designed around
(no code path relies on RLS as a backstop; every current test proves
isolation at the repository layer already). Adding it now would be
"speculative infrastructure without justification" (per this phase's own
instruction) — a legitimate defense-in-depth idea for a future,
security-focused phase, but one that needs its own design (which
PostgreSQL role the application connects as, how `current_setting('app.org_id')`
gets set per-request, policy definitions per table) rather than being
bolted on inside a persistence-architecture pass. **If added later**, it
should be additive — the application-level filtering must remain, RLS
becomes a second, independent backstop, not a replacement.

## 8. Audit data persistence — verified, one item flagged for future work

Confirmed (Phase 2 audit, still true): `AuditRepository`'s Protocol
exposes only `record()` (insert) and read methods — no `update`, no
`delete`, anywhere in its interface or either implementation. Zero
`UPDATE`/`DELETE` SQL statements touch `audit_events` anywhere in this
codebase (grepped directly).

**Not implemented, flagged rather than built speculatively**: PostgreSQL-level
permission grants (e.g. `REVOKE UPDATE, DELETE ON audit_events FROM
application_role`) would add real defense-in-depth against a compromised
or buggy application process mutating audit history directly via SQL,
independent of the Python-level API surface. This requires deciding the
application's actual PostgreSQL role/grant model, which does not exist yet
(the current `DATABASE_URL` connects as a single role with full
privileges) — a decision for a dedicated security-hardening phase, not
invented here without that context.

## 9. Evidence persistence — metadata vs. content, verified separation; blob storage flagged as future work

`evidence_records` stores **metadata only**: `file_hash` (sha256 of the
uploaded content), `original_filename`, `content_type`, `size_bytes`,
status/lifecycle fields, and linkage references. It does not, and per the
existing architecture should not, store the evidence file's actual bytes —
no `BYTEA`/large-object column exists anywhere in `schema.sql` for this
table, confirmed by direct inspection.

**Not yet implemented, explicitly flagged as future work rather than
invented here**: where the actual file content is stored in production
(object storage such as S3-compatible storage is the natural fit, keyed by
`file_hash` or the record's `id`) is not yet decided or built. The
Evidence Vault's domain/service layer (`EvidenceVault.upload_evidence`)
currently accepts raw `bytes` and computes `file_hash` from them, but
nothing downstream of that persists the bytes anywhere durable in the
PostgreSQL path — only the SQLite test path exists at all, and even there,
content bytes are not currently persisted separately from the test's own
in-memory fixtures. This is a real, acknowledged gap for a dedicated
"Evidence Storage" phase (already named as Phase 8 in the broader
production-completion roadmap), not something to improvise inside a
database-architecture pass.

## 10. Database configuration — verified minimal and correct

`.env.example` declares exactly one variable the application actually
reads: `DATABASE_URL` (confirmed: `api/db/base.py` is the only place
`os.environ.get` is called for configuration). No secret is exposed (it's
a local-development placeholder). No additional configuration variable was
added speculatively — auth needs no separate secret, since sessions are
opaque, database-backed tokens (SHA-256 hash of a random value), not
JWT-signed, so there is no `SECRET_KEY` for the application to manage.

## 11. Health vs. readiness — fixed during this audit

Previously only `/health` existed, and it never touched the database — a
correct **liveness** check, but with no corresponding **readiness** check,
meaning an orchestrator relying on it alone could route real traffic to an
instance with no working database connection.

**Fixed**: `/health` (liveness — process alive, no dependencies, always
fast) and `/ready` (readiness — executes a real `SELECT 1` against the
actual request-scoped session; returns `503` with the underlying error on
failure, `200 {"status": "ready"}` on success) are now both defined, with
the distinction verified structurally (`/health` takes zero dependencies;
`/ready` depends on `get_session` and contains both a query execution and
explicit failure handling).

---

## Required external runtime environment

Same as `docs/runtime-verification.md`, plus, for migrations specifically:

```
alembic>=1.13
sqlalchemy>=2.0
psycopg[binary]>=3.1
```

## Exact commands for real PostgreSQL/migration verification

```bash
cd asavexa

# 1. Environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# edit .env — set DATABASE_URL to a real, reachable PostgreSQL instance
export DATABASE_URL=postgresql+psycopg://asavexa:asavexa@localhost:5432/asavexa

# 3. Apply the initial migration (this is what actually creates every
#    table — do NOT also run `psql < schema.sql` separately, or the
#    second attempt will fail on already-existing tables)
alembic upgrade head

# 4. Confirm Alembic's own version tracking is correct
alembic current
# expect: 9ab0a651f090 (head)

# 5. Confirm the domain suite still passes unchanged (works in any
#    environment, dependencies or not — proves nothing about this step
#    broke the parts of the app that don't touch PostgreSQL)
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 6. Start the real application
PYTHONPATH=src uvicorn asavexa.api.main:app --reload

# 7. In another shell, confirm both liveness and readiness for real
curl http://localhost:8000/health
# expect: {"status":"ok","modules":[...]}
curl http://localhost:8000/ready
# expect: {"status":"ready"}   (or 503 with a real error if PostgreSQL
# is unreachable — that response itself is the readiness check working)

# 8. Exercise a real multi-write operation and confirm atomicity: stop
#    PostgreSQL mid-request (or otherwise force a failure between two
#    writes in one service operation) and confirm nothing partially
#    persists — the request-scoped rollback in get_session() should
#    make this true by construction; verifying it for real against a
#    live database is the one thing this document cannot do for you.

# 9. Test the downgrade path in a disposable database before ever
#    relying on it in production
alembic downgrade base
```

At that point — and only at that point — the items this document and its
companion mark "not verified" can be moved to "verified," because they
will have actually executed against real PostgreSQL, real Alembic, and
real SQLAlchemy.
