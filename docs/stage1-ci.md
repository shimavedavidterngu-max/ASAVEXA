# Stage 1: continuous integration (GitHub Actions)

One workflow: `.github/workflows/ci.yml`. It runs on **every push and every pull request**. It never deploys, uses **no production secrets**, and its only database is a throwaway PostgreSQL 16 container created for the run.

| Job | What it proves | Status |
|---|---|---|
| **Unit, contract and security tests** | All server tests (about 1,290), including the route-security audit, audit-coverage, tenant-isolation, migration and backup tests, with real PostgreSQL so none is skipped. Fails if a PostgreSQL test is skipped | IMPLEMENTED, NOT YET RUN on GitHub |
| **Real stack (FastAPI + SQLAlchemy + Alembic + PostgreSQL)** | `alembic upgrade head` (twice), schema parity, down/up round trip, then every route over HTTP: no-token requests, and a second organisation attacking the first with its real identifiers | IMPLEMENTED, NOT YET RUN on GitHub |
| **Frontend tests** | The 785 frontend tests | IMPLEMENTED, NOT YET RUN on GitHub |

## Honest expectation for the first run
The real-stack job has never run anywhere (this sandbox cannot install FastAPI or SQLAlchemy). **Expect it to need one or two fixes on its first run**, for example an environment value the app wants at start-up. A red first run is information, not a failure of the plan; send me the log and I will fix it.

## Secrets
None are used. The CI database password in the file is a fixed test value for a container that is destroyed at the end of the run. Do not add real URLs or keys to this file. If a future job needs a secret, store it under GitHub → Settings → Secrets and variables → Actions.

## Make passing tests required before merging (your action, in GitHub)
1. Push this change and wait for the first runs to finish (the check names only appear in the list after they have run once).
2. GitHub → your repository → **Settings → Branches → Add branch ruleset (or rule)** for `main`.
3. Turn on **Require status checks to pass** and select the three checks above.
4. Optionally turn on **Require a pull request before merging**.

**What this changes for you:** with the rule on, `git push` straight to `main` is refused. You would push to a branch and merge through a pull request once the checks are green. Because that changes your daily flow, I suggest leaving the rule **off** until you have seen CI go green on a few ordinary pushes, then turning it on. This is your decision.

## Running the same tests yourself
- Server: `PYTHONPATH=src:tests python -W ignore -m unittest discover -s tests`
- Add real PostgreSQL tests: set `ASAVEXA_TEST_PG_URL` to a **throwaway** server (they create and drop databases named `bk_*` and `s1mig_*`).
- Frontend: `cd frontend && node --test tests/*.test.js`
- Real stack: see the header of `tests/stack/test_two_tenants_http.py` (needs `pip install -r requirements.txt`, a throwaway `DATABASE_URL`, `alembic upgrade head`, `ASAVEXA_STACK_TEST=1`). It refuses any database that is not localhost/CI.
