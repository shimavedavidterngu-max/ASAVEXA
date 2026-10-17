# Stage 34: Operations research

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a finance or operations-research professional.

## What it is
A decision-analysis workspace for the gap the Phase-1 audit listed as a missing workspace, **operations research**: an **analysis** compares two to eight **options**, each with a typed upfront cost and a typed net flow for each of one to ten years, at a typed yearly discount rate. **Net value, discounted value (NPV), payback year, benefit-cost ratio and the NPV at the rate two points lower and higher are worked out exactly.** A different person reviews the analysis, and the choice made is recorded with its reason. **It recommends nothing, decides nothing, forecasts nothing and moves no money.**

Screen: **Operations research** (menu, under Professional workspaces). API prefix `/oprs`. Stored in the shared document store (kinds `op_analysis`, `op_setting`). Reference numbers: OA- (analyses). Service methods are prefixed `op_`.

## What it does
1. **Analyses.** A title, a purpose (what is being decided), a three-letter currency and a discount rate (percent a year, 0 to 100, at most two decimals). Statuses: Draft, Waiting for review, Approved, Returned, Withdrawn.
2. **Options.** A name (unique among the options in use), an upfront cost (more than zero) and the net flow (benefit less running cost; may be zero or negative) for each year, from 1 to 10 years. At most eight options in use. A wrong option is removed with a reason (kept) and entered again.
3. **Results, worked out with exact fractions and rounded to two decimals only for display (half away from zero):** total flows, net value (flows less upfront cost), NPV at the typed rate (each year's flow discounted at the end of the year), payback year (the first year the running total reaches the upfront cost, or none), benefit-cost ratio (total flows over upfront cost), rank by NPV (ties share a rank) and NPV at the rate two points lower and two points higher (skipped if that rate would be below zero). The option(s) with the highest NPV are marked as a number, not as advice.
4. **Review.** A draft or returned analysis is submitted (needs at least two options in use). **A different person approves it, or returns it with a reason.** An approved analysis is final.
5. **Decision.** After approval, an approver who is not the submitter records which option was chosen and why (at least 10 characters), once. Choosing an option that did not have the highest NPV is **flagged for a person to look at, never blocked**.
6. **Overview.** Counts by status, decisions recorded, approved analyses per currency (never added together) and a list of items for a person to look at.

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`oprs:prepare`: start analyses, add and remove options, submit, withdraw): Owner, Administrator, Manager, Auditor.
- Approve (`oprs:approve`: approve or return analyses, record the decision): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who submitted an analysis can never be the one who approves, returns or records the decision on it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not titles, purposes, option names, figures, reasons or notes.

## What it does NOT do
- It forecasts nothing and checks no cost, flow or rate against the real world. Every figure is typed by a person; a different person approving is a review of what was typed.
- The highest NPV is a number, not advice. Risk, funding, timing within a year, inflation, tax, currency changes and everything not typed in are left out. It applies no investment, public-sector or accounting standard.
- Flows are whole years discounted at the end of the year. It is not a general optimisation or simulation tool.
- An approved analysis cannot be edited; a changed assumption is a new analysis. Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_oprs.py` (26 tests; NPV, net value and benefit-cost checked against an independent fraction calculation across six rates, including rounding on the half-cent boundary) plus the static route-security, audit-coverage, tenant-isolation, boundary and router-names tests; an odd-input run (493 calls) found no crashes.
- Frontend: `frontend/tests/oprs.test.js` (15 tests).
- Browser: `e2e/journey_oprs.py` (63 checks across Accountant, Administrator, Approver and Owner sign-ins, comparing the page with exact figures).
