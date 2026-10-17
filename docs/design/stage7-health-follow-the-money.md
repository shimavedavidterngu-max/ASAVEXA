# Stage 7: Health administration, "Follow the money"

Status: built and tested in the test environment. **Not deployed; CI and Render results not yet confirmed.**

## What it is
A new tab, "Follow the money", in the Health Centre workspace. For one department it shows the chain **authorised -> purchased -> delivered -> still unresolved** as a Ledger Paper page (`data-sector="health"`) with a four-step Proof Rail beside it.

## Honesty rules (all tested)
- Finance and administration only. No patient field on the tab or in the code that builds it.
- Nothing is added up or recalculated in the browser. Amounts are the server's own strings (budget execution, purchase orders, invoices).
- A list that could not be loaded is "Not checked", never an empty list that reads as clean. No approved budget is "missing", not zero.
- Delivery is a person's record. The tab says ASAVEXA has not confirmed that anything arrived, and it does not buy, pay or approve anything (no buttons in the ledger).
- State is carried by shape and words: solid (linked), half (in progress), hollow-dashed (not linked / needs a decision).

## Files
- `frontend/src/lib/healthTrace.js` (pure), `frontend/src/pages/Health.js` (view), `frontend/src/app.js` (`loadHealthTrace`, `setTraceDept`), `frontend/src/lib/health.js` (tab).
- Tests: `frontend/tests/healthtrace.test.js` (24).
- Browser: `e2e/journey_health_trace.py` (25 checks) with `e2e/health_seed.py` (builds the centre through the real health service, by different people).
- Test server: `e2e/server.py` now serves `/health/*` by running the REAL health router functions and service; the route table is read from the router's own decorators. `tests/harness_security_routers.py` gained `get_health`.

## Not checked
Real devices, screen readers, other browsers, performance, the live site.
