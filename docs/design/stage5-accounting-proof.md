# Stage 5: the proof behind a statement line (accounting)

Status: VERIFIED IN TEST ENVIRONMENT, NOT DEPLOYED.

## What changed
- Trial Balance, Income Statement and Balance Sheet lines each get a proof mark. Before it is opened it says "Proof not checked" and claims nothing. Opening it loads, for that one account and period, the posted entries, evidence completeness and reconciliation summary (three read-only calls) and shows them in the Proof Rail beside the statement. The mark then shows what was found (complete, incomplete, none).
- Reconciliation is left out for accounts that are not reconciled bank accounts (not applicable is not a gap). A failed call shows "Not checked"; a failed trace load claims nothing and offers Try again.
- No figure is computed in the browser: counts are the server's own, only worded.
- Keyboard: focus moves into the rail on open, Escape or Close returns it to the mark; Enter on a mark does not also trigger the row's drill-down.
- Defect fixed: report amounts were formatted by converting to a floating-point number (rounding large or 4-decimal amounts). They now display digit for digit as the server sent them.
- Defect fixed: on a phone the Trial Balance and Income Statement summary row overflowed the screen sideways.
- Test harness only: the end-to-end test server now serves /accounts and /reports/* through the real reporting router and service; one stand-in (`Query`) was added to the FastAPI stand-in.

## Measured here
- Frontend suite 1414/1414. Python suite 2331 run, OK (8 PostgreSQL skips). Release check 10/10.
- New real-backend browser journey: 20/20 (and it fails when the Enter-key protection is removed).
- Existing 32 journeys: all passed on the Stage 4 code. A full re-run of all 33 on the Stage 5 code was started and is not finished at the time of writing.
- No horizontal overflow at 390px; light and dark screenshots checked.

## Not checked
Real devices, screen readers, other browsers, performance, the live site. The ledger page (Accounting) and the reconciliation page were not redesigned in this stage.
