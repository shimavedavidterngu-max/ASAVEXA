# Stage 14: grants matched to programme results

Until now Public Finance said it did not link a grant to programme results. Stage 14 adds a link that is deliberately modest: **a typed reference**, not a verified one.

## What it does
- A grant can carry an optional **programme reference** (2 to 40 characters), typed when it is recorded or later by a preparer while the grant is active: `PUT /pubfin/grants/{id}/programme`, audited as `PF_GRANT_PROGRAMME_SET` (and `PROGRAMME_REF_SET` in the grant history). Empty removes it. Existing grants simply have none.
- "Follow a grant" / "Follow a fund" gains a **Programme results** section. It lists the approved Impact indicators whose own programme reference is the same code (ignoring capitals and spaces), each in the server's own words and figures: state, latest confirmed reading and its period end, and progress.
- Honest states: no reference typed; **Not checked** (impact indicators could not be loaded, for example no permission to see them); no approved indicator with that code; or the matches.
- The editing control sits outside the read-only ledger.

## What it does not do
- It does not show that the grant caused any change. The page says so next to the result.
- It does not verify readings, and it does not check amounts against targets.
- Proposed, rejected and closed indicators are not matched.
- Indicators are not changed by this stage; the Impact module is untouched.

## Tests
Python: 4 new (`GrantProgramme`) plus the router guard list. Frontend: `programmelink.test.js` (21). Browser: `e2e/journey_pubfin_programme.py` (16 checks, fresh server, real Impact routes with different people proposing, approving and confirming).
The old footer "does not link the grant to programme results" was reworded because it was no longer true.
