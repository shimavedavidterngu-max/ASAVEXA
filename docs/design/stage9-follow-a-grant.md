# Stage 9: Public Finance, "Follow a grant" (nonprofits and funders)

Status: built and tested in the test environment. **Not deployed; CI and Render results not yet confirmed.**

## What it is
A new tab, "Follow a grant". Choose a grant; it reads as a plain sentence ("Of the 20,000.00 USD awarded by Water Fund (restricted), 12,000.00 USD has been received and 5,000.00 USD of spending is approved. 1,000.00 USD more is waiting for a second person to approve it. 15,000.00 USD of the award is still unspent."), a figures table, the spending entries, and a four-step Proof Rail: funding awarded -> cash received -> spent (approved) -> evidence.

## Honesty rules (all tested)
- Figures are the server's own (received, spent, pending, remaining, cash held); nothing is added or compared as a number in the browser (a test fails if arithmetic appears).
- Spending waiting for a second person is shown as waiting, never as spent. Spending above the cash recorded as received is flagged in words.
- Restriction and conditions are shown as entered. The page states it does NOT judge whether donor conditions are met and does NOT link the grant to programme results (activities, outputs, outcomes); that link does not exist yet.
- Read view only: no buttons in the ledger.

## Files
`frontend/src/lib/grantTrace.js`, `frontend/src/pages/Pubfin.js`, `frontend/src/lib/pubfin.js` (tab), `frontend/src/app.js` (`followGrant`), `frontend/src/styles/ledger.css` (row headers in statement tables), `frontend/tests/granttrace.test.js` (15), `e2e/journey_pubfin_grant.py` (23 checks).

## Not checked
Real devices, screen readers, other browsers, performance, the live site. Evidence linking is unit-tested only: the test server has no evidence upload, so the browser journey shows the "not linked" states.
