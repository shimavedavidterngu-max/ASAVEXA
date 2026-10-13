# Stage 8: release hardening and how to verify a release

Status: **IMPLEMENTED; checks run in the sandbox; CI workflow for browser journeys NOT RUN.**

## Added
- `e2e/`: the browser journeys now live in the repository (Evidence Review, Standards Registry, Agents), with a test server that runs the real routers and services without PostgreSQL. `PYTHONPATH=src:tests python3 e2e/run_all.py` (needs `pip install playwright && playwright install chromium`; set `CHROMIUM_PATH` to use an existing Chromium). Closes risk R11 for these journeys. The earlier sign-up, sign-in, onboarding and dashboard journeys are still outside the repository.
- `scripts/release_check.py`: an offline readiness check (code compiles, one migration chain and head, every router mounted, no secret-looking values, docs and tests present). Exit code 0 is not "production ready".
- `.github/workflows/e2e.yml`: runs the journeys in GitHub Actions, **manual trigger only** until it has been seen to pass.

## Verify a release (run these, one at a time)
1. `python3 scripts/release_check.py`
2. `PYTHONPATH=src:tests python3 -W ignore -m unittest discover -s tests` (about 4 minutes; set `ASAVEXA_TEST_PG_URL` to a throwaway PostgreSQL to include the PostgreSQL tests)
3. `cd frontend && node --test tests/*.test.js`
4. `PYTHONPATH=src:tests python3 e2e/run_all.py`
5. `python3 scripts/ai_eval.py`
6. Against production, yourself: `python scripts/db_preflight.py`, a verified backup, then `alembic upgrade head`.

## Still not proven
Real FastAPI/SQLAlchemy/Alembic runs (the CI "Real stack" job has never run), Render/Vercel settings, email delivery, load and accessibility testing, and an independent security review.
