# Stage 1 test report (2026-10-12)

Scope: Stage 1 only (verify before building). Stage 2 has not been started. **Nothing has been deployed and nothing has been run against production.** Production readiness is **not** claimed.

Status words: NOT STARTED / IN PROGRESS / BLOCKED / IMPLEMENTED, TESTS PENDING / VERIFIED IN TEST ENVIRONMENT / VERIFIED IN STAGING / VERIFIED IN PRODUCTION / INDEPENDENTLY REVIEWED.

## 1. Baseline, before any change
| Check | Passed | Failed | Skipped | Blocked |
|---|---|---|---|---|
| Server suite | 1,230 | 0 | 3 (PostgreSQL backup/restore: no PostgreSQL available then) | none |
| Frontend suite | 785 | 0 | 0 | none |
| Browser journeys (email 31, auth 75, onboarding 66, dashboard 68) | all | 0 | 0 | none |

## 2. After Stage 1
| Check | Passed | Failed | Skipped | Blocked |
|---|---|---|---|---|
| Server suite, with a real PostgreSQL 16 test server | **1,294** | 0 | **0** | none |
| Frontend suite | **785** | 0 | 0 | none |
| Browser journeys, real routers over HTTP (email 30, auth 74, onboarding 65, dashboard 67 checks; 4 "all passed" summaries) | **236 checks** | 0 | 0 | none |
| Real-stack HTTP tests (`tests/stack/`, 4 tests) | not run | – | 4 skipped here by design | **BLOCKED in this sandbox**: FastAPI/SQLAlchemy cannot be installed (no route to PyPI). Run in GitHub Actions |
| GitHub Actions workflow | not run | – | – | **BLOCKED here**: it can only run on GitHub |
| Alembic itself (`alembic upgrade head`) | not run | – | – | **BLOCKED here**: Alembic/SQLAlchemy/psycopg not installable. The migration SQL was run on real PostgreSQL through `psql`; the revision's Python is unit-tested with a stand-in |
| `scripts/schema_parity.py`, `scripts/db_preflight.py` against a database | not run | – | – | **BLOCKED here** (need SQLAlchemy). The preflight's advice logic and read-only/no-URL guarantees are unit-tested (4 tests) |

The 3 previously skipped tests now run and pass on PostgreSQL 16: backup, integrity verification, restore round-trip, tamper detection (`tests/test_backup.py`).
New tests added in Stage 1: 61 server tests (migrations 18, route security 13, audit coverage 7, tenant isolation 10, AI seam 6, preflight 4, health audit 3), so 1,233 + 61 = 1,294. Eight existing tests were adjusted because the design changed: five asserted 'tables are created at start-up' and three asserted 'exactly one migration exists'.

## 3. Acceptance conditions
| Requirement | Result |
|---|---|
| Existing suite on a real PostgreSQL | **VERIFIED IN TEST ENVIRONMENT** for everything that touches PostgreSQL directly (backup, restore, schema, migrations). The *real FastAPI + SQLAlchemy* part is **IMPLEMENTED, NOT RUN** (CI) |
| Two-tenant isolation tests | Service level, 10 tests: **VERIFIED IN TEST ENVIRONMENT**. Every route over HTTP: **IMPLEMENTED, NOT RUN** (CI) |
| Cross-tenant access denial | A's accounting, evidence, reconciliation, compliance, membership and session data attacked by B's owner with A's real identifiers; all refused; A's data and audit trail byte-identical afterwards. A control test proves the same calls work for A |
| Audit-event coverage | Static, all 313 authenticated write routes: 306 reach an audit-trail write, 7 reviewed as intentionally not (previews, calculator, drafts). **14 real gaps found and fixed** (below). Dynamic tests prove each fixed action now logs exactly one event naming the actor |
| Startup table creation moved into migrations | **IMPLEMENTED; SQL VERIFIED IN TEST ENVIRONMENT**; Alembic run itself pending in CI |
| Migrations documented with rollback | `docs/stage1-migrations.md` |
| Backup / rollback plan | `docs/stage1-migrations.md` section 5; restore drill **VERIFIED IN TEST ENVIRONMENT** (not on Render) |
| GitHub Actions, isolated DB, no production secrets | `.github/workflows/ci.yml`, `docs/stage1-ci.md`. **IMPLEMENTED, NOT RUN** |
| Tests required before merging | Needs your GitHub setting (instructions in `docs/stage1-ci.md`). **NOT DONE by me; your action** |
| AI stays rule-based, interface for later | `src/asavexa/ai/provider.py`, `docs/ai-provider-gate.md`. No outside model integrated or selectable |
| Production database verified | **NOT DONE: cannot be from here.** A read-only preflight script and checklist are provided for you to run |

## 4. What the audits found
**Route security (533 routes, static, every route):**
- 24 routes need no sign-in; each is reviewed and listed with its protection (login, register, recovery, webhook signature, share-link tokens, health probes, static guides). Any new unprotected route now fails the build.
- 0 routes take an organisation id from a request body, query or form. 4 routes name an organisation in the path (membership management); each is authorised against the caller's role in that organisation, and tested.
- 11 authenticated write routes have no `require_permission`; each is reviewed (inline permission checks, the caller's own account, stateless previews).
- The inventory first missed the 6 routes on `org_router` and `txn_router`; fixed, and the count now matches the 533 in the Stage 0 audit.

**Audit coverage, real gaps fixed (additive, one log call each):**
Health: requisition edit, quote added, stock issued, stock transferred, asset condition set, asset evidence linked, maintenance cancelled. Security: alert acknowledged, vendor added / updated / seeded, recovery codes regenerated, session revoked, other sessions revoked. These changed data but wrote nothing to the organisation audit trail (health actions kept only the record's own history).
Limit: the static scan shows an audit call is *reachable* from a route, not that every branch makes it. The dynamic HTTP version is in CI.

**Tenant isolation:** no cross-tenant defect found at the service level. This is **not** proof for every route: only the real-stack test can show that, and it has not run.

## 5. Exact commands and results
| Command (from the project folder) | Result |
|---|---|
| `ASAVEXA_TEST_PG_URL=postgresql://postgres@127.0.0.1:5544/postgres PYTHONPATH=src:tests python3 -W ignore -m unittest discover -s tests -v` | `Ran 1294 tests in 210.9s` `OK` (0 skipped) |
| `cd frontend && node --test tests/*.test.js` | `tests 785, pass 785, fail 0` |
| `PYTHONPATH=src:tests python3 -m unittest discover -s tests/stack -p "test_*.py"` | `Ran 4 tests`, `OK (skipped=4)`: BLOCKED, see above |
| `psql -f schema.sql` then `-f migrations/sql/b7c1d2e3f4a5_late_tables.up.sql` (twice) on PostgreSQL 16 | 17 tables, then 23 tables, second run no change |
| `pg_dump -Fc` then `pg_restore` into a new database | counts 2/1/2/1 and content checksums identical |
| Browser journeys (Chromium against the real routers over HTTP, sandbox-only scripts) | email 30, auth 74, onboarding 65, dashboard 67 checks passed, 0 failed |
In CI the unit job sets `ASAVEXA_TEST_PG_URL` to its own throwaway PostgreSQL container, so the same command runs there.

## 6. Not done, on purpose
- Not deployed; Stage 2 not started; no production database operation; no outside AI model.
- The browser journey scripts still live outside the repository (Stage 0 item R11). They are not part of CI.
- Rate limits are still in memory per server instance (Stage 9).
