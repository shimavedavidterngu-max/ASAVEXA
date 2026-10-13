# Stage 2 test report

Run on 2026-10-12/13 in the development sandbox (no FastAPI/SQLAlchemy; routers run through stand-ins, SQLite for services, real PostgreSQL 16 for the PG tests).

| Check | Command | Result |
|---|---|---|
| Server suite incl. PostgreSQL tests | `PYTHONPATH=src:tests python3 -W ignore -m unittest discover -s tests` with `ASAVEXA_TEST_PG_URL` set | 1314 tests, OK |
| Frontend suite | `cd frontend && node --test tests/*.test.js` | 807 of 807 pass |
| Browser journey (Chromium, real router functions over HTTP, SQLite stand-in server) | evbrowser.py (outside repo) | 31 checks pass |

Bugs found by testing and fixed: (1) the review found no evidence because the sample reporting service had no vault; the engine now takes the vault explicitly; (2) in the browser, `#/evidence-review` opened the Evidence Vault because the page dispatcher matched any name starting with "evidence"; fixed and covered by a test.

Not verified: real FastAPI, SQLAlchemy store on PostgreSQL for case records, GitHub Actions, Render, any deployment.
