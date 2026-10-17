# Stage 8: Public Finance, "Where the money went" (schools, public bodies, any budgeting organisation)

Status: built and tested in the test environment. **Not deployed; CI and Render results not yet confirmed.**

## Scope, honestly
There is no school-specific backend. Schools and public bodies budget in Public Finance (approved budgets, commitments, ledger actuals), so this stage reads that. A budget line is an **account**, not a department: the view does not invent departments. A school that names its accounts by department sees them that way.

## What it is
A new tab, "Where the money went". Choose an approved (or closed) budget; each expense line reads as a plain sentence, for example: "Of the 500,000.00 NGN approved for 5000 Rent, 200,000.00 NGN has been spent (posted to the ledger), 1,500.00 NGN is promised in open commitments, and 298,500.00 NGN is still available." The line's Proof Rail shows authorised -> promised -> spent (posted) -> evidence. Income lines are listed separately. The accent follows the organisation's sector (school, university, government...).

## Honesty rules (all tested)
- Amounts are the server's own strings; nothing is added, subtracted or compared as a number in the browser (a test fails the build if arithmetic appears).
- "Spent" means posted to the ledger; a promise is never shown as spent. ASAVEXA says it made no payment.
- A budget or commitment list that could not be loaded is "Not checked", never zero; nothing promised is said plainly.
- Over budget is shown in words and as a badge, never only by colour, and the sentence has no minus sign.
- Read view only: no approve, settle, cancel or pay buttons in the ledger.

## Files
- `frontend/src/lib/spendTrace.js` (pure), `frontend/src/pages/Pubfin.js`, `frontend/src/lib/pubfin.js` (tab), `frontend/src/app.js` (`pubfinSpendLoad`, `spendBudget`, `spendLine`).
- Tests: `frontend/tests/spendtrace.test.js` (21).
- Browser: `e2e/journey_pubfin_spend.py` (24 checks).
- Test server: `e2e/server.py` now also serves `/pubfin/*` by running the REAL router functions and service, with the route table read from the router's decorators. `tests/harness_security_routers.py` gained `get_pubfin`.

## Not checked
Real devices, screen readers, other browsers, performance, the live site. The browser journey has one expense account in the test world, so switching between several expense lines is covered by unit tests, not the browser.
