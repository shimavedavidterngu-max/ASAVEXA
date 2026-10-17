# Stage 35: Impact measurement

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a monitoring-and-evaluation professional.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **impact measurement**: programme **indicators** (what is measured, a baseline and a target, with dates), the **readings** people report against them, and **progress toward the target and the progress expected by today, worked out exactly**. A different person approves each indicator and confirms each reading. **It collects no data, verifies no result, applies no framework or standard and shows nothing about what caused a change.**

Screen: **Impact measurement** (menu, under Professional workspaces). API prefix `/impact`. Stored in the shared document store (kinds `imp_indicator`, `imp_setting`). Reference numbers: IM- (indicators). Service methods are prefixed `imp_`.

## What it does
1. **Indicators.** A title, a programme reference code, a unit (for example households), a direction (increase or decrease), a baseline and a target value (non-negative, at most two decimals) and their dates (the target date after the baseline date, at most ten years apart; for an increase the target is higher than the baseline, for a decrease lower). **Proposed by one person and approved or rejected by a different person.** Statuses: Waiting for a decision, Open, Rejected, Closed.
2. **Readings.** On an open indicator, a period-end date (not in the future, not before the baseline date), a value and a source note saying where the figure came from. **Recorded by one person and confirmed or rejected by a different person.** Only confirmed readings count. There is at most one live reading per period end; a rejected reading frees its period for a new one.
3. **Progress, exact.** Progress is `(latest confirmed value - baseline) / (target - baseline)` as a percentage with two decimals (negative when moving the wrong way, above 100 when the target is passed). The **expected progress by today** is the share of the days between the baseline and target dates that has passed (0 before the baseline date, 100 after the target date).
4. **State of an open indicator.** Target reached (progress 100 or more), On track, Behind (progress more than your tolerance in percentage points below expected), Target date passed (past the target date without reaching it) or No reading yet. Comparisons use exact fractions.
5. **Closing.** An approver closes an open indicator with a reason once no reading is waiting. A closed indicator takes nothing more.
6. **Overview and settings.** Counts, open indicators by state, a list of items for a person to look at (indicators and readings waiting, behind, target date passed, readings stale, no reading yet) and two of your own settings: the tolerance (0 to 100 percentage points, default 10) and the days after which the latest confirmed reading is stale (1 to 730, default 120).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`impact:prepare`: propose indicators, record readings): Owner, Administrator, Manager, Auditor.
- Approve (`impact:approve`: approve, reject or close indicators, confirm or reject readings, change the settings): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who proposed an item can never be the one who decides it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not titles, programme references, units, values, source notes or reasons.

## What it does NOT do
- It collects no data and connects to no survey, sensor or system. A confirmed reading is a recorded review of a typed number, not evidence that the number is true.
- Progress is arithmetic only. It does not show that a programme caused a change, and it does not measure quality, equity, side effects or cost-effectiveness. No logframe, theory of change or reporting standard is applied.
- Expected progress assumes steady change between the two dates. Real programmes are rarely steady, so Behind and On track are prompts for a person to look, not findings.
- Units are kept as typed and never combined across indicators. Baselines and targets cannot be edited after approval; a change is a new indicator.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_impact.py` (26 tests; progress and expected progress checked against an independent fraction calculation, tolerance boundaries on the cent, stale and overdue boundaries on the day) plus the static route-security, audit-coverage, tenant-isolation, boundary and router-names tests; an odd-input run (660 calls) found no crashes.
- Frontend: `frontend/tests/impact.test.js` (14 tests).
- Browser: `e2e/journey_impact.py` (70 checks across Accountant, Administrator, Approver and Owner sign-ins).
