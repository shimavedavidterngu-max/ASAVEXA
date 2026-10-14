# Stage 18: Planning and KPIs (FP&A extensions)

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not independently reviewed.

## What it is
A records-and-checks workspace for two things: **KPIs with a named owner and a traceable source**, and **forecast accuracy**. **It does not calculate a KPI from the ledger, does not check that a number is true, and does not predict anything.** It keeps who owns each KPI, who recorded each reading, where they say it came from, who reviewed it, and how past forecasts compared with what actually happened.

Screen: **Planning and KPIs** (menu, under Professional workspaces). API prefix `/fpa`. Stored in the shared document store (kinds `fp_kpi`, `fp_reading`, `fp_forecast`, `fp_setting`). Reference numbers: KP-, KR-, FC-.

## What it does
1. **KPI definition.** Name, what it measures, unit (amount, ratio, percent, count, days), currency (amounts only), which direction is better, how often it is measured (monthly, quarterly, annual), a typed-in target, where the number comes from, how it is calculated, and a start date. The close-to-target margin is fixed on the KPI when it is defined.
2. **One named owner.** The owner must be an active member whose role can record readings, and must **accept** ownership before any reading is recorded. Only the owner records readings. The person who defined a KPI cannot approve it, and the owner cannot approve the target they are measured against. The person who approved a target cannot later become its owner. An approver may change the owner (with a reason); the history is kept.
3. **Readings with a source.** Every reading carries a written source note (at least 10 characters) and, optionally, documents from the Evidence Vault (their file fingerprints are kept). A reading with no document is shown as such. A **different person** reviews or rejects each reading. A second reading for the same period is a **correction**: it needs a reason, replaces the old one, and the old one is kept.
4. **Periods.** Monthly and quarterly readings must end on a calendar month or quarter end; annual ones on any date. A reading cannot be dated before the KPI's start or in the future.
5. **Target judgement.** Fixed arithmetic against the typed target: on target, close to target (short by no more than the margin, as a percentage of the target) or off target. A target of zero is handled without dividing by zero.
6. **Forecasts.** Registered with a metric, unit, a period that has **not yet ended**, a value and a written basis. **The system stamps today's date**; it cannot be typed, back-dated or edited. A forecast can only be withdrawn, and only by the person who made it.
7. **Actuals and accuracy.** After the period ends, someone **other than the forecaster** records the actual with a source, and a **third person** (not the recorder, not the forecaster) confirms it. Accuracy counts **confirmed actuals only**. Error is forecast minus actual; the accuracy band is fixed when the forecast is registered. Per metric, unit and currency the page shows WAPE, bias, mean absolute error, how many ran high, low or exact, and the hit rate; it says plainly when there are too few items to mean much. A minimum-lead-time filter excludes forecasts made too close to the period end. Hit rates are shown per forecaster only as counts and rates, not rankings.
8. **Policy settings** (approvers only): default close-to-target margin, days of grace before a reading is overdue, accuracy band, and the minimum number of items before accuracy is called meaningful. Defaults are placeholders.
9. **Overview.** A "what needs attention" list: targets and ownership waiting, overdue and off-target KPIs, readings to review, readings with no document, actuals due and waiting for confirmation, and a forecast bias warning; plus a per-owner table.

## Who may do what
- View: `reporting:read` (everyone who can see the ledger).
- Prepare (define KPIs, accept ownership, record readings as owner, register and withdraw forecasts, record actuals): `fpa:prepare` — Owner, Manager, Finance Officer, Accountant.
- Approve (approve and retire KPIs, change owner, review or reject readings, confirm or reject actuals, change settings): `fpa:approve` — Owner, Manager, Finance Officer, Approver.
- Separation is enforced by the service for every role, including the Owner.

## What it does NOT do
- It does not calculate a KPI from the ledger or any other system, and does not verify a reading, a target or an actual. It records what people type in and who said it.
- A target judgement says nothing about whether the target is a good one.
- Accuracy describes the past; it is not a forecast, and with a handful of items it means little.
- Units and currencies are never added together or converted.
- A target cannot be edited: retire the KPI and define a new one (the old history stays).
- It does not post to the ledger and is not an audit opinion or a performance guarantee.
- Two people sending the same request at the same instant are not guaranteed to be caught by the duplicate checks, and nothing has been load-tested.
- Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Found and fixed while testing
- **Real defect, found by a test and fixed:** two readings saved at the very same instant had the same sort key, so their order depended on a random internal key (the test failed intermittently). Records are now ordered by a numeric reference tie-break (so KP-1000 sorts after KP-999), for readings, KPIs and forecasts, with a regression test.
- **Known, low impact, not changed:** Treasury and Procurement still sort their reference numbers as text, so their order differs from numeric order only past 999 items of one kind.
- Every other failure in the first runs was a mistake in my own tests or journey (a helper that dropped the currency, a target that was in fact valid at two decimal places, a date taken in local rather than UTC time, a check that read the screen before it had reloaded after the test clock moved). The product rules behaved as designed.

## Verification (test environment only)
- Server: `tests/test_fpa.py` (48 tests: helpers, settings, KPI definition and approval separation, ownership, readings and corrections, forecasts, accuracy arithmetic, overview, company isolation, audit trail, permissions, route guards and number handling) plus the static route-security and audit-coverage checks.
- Frontend: `frontend/tests/fpa.test.js` (28 tests: permissions, payload builders, which buttons each person sees, every tab for every role, client paths, menu wiring).
- Browser: `e2e/journey_fpa.py` (46 checks across Accountant, Owner and Approver sign-ins, including the server refusing what the buttons hide, a second company seeing nothing, and the audit actions).
- The test-only clock hook in `e2e/server.py` exists only in the test server.
