# Stage 37: Pension and fiduciary

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a pensions professional or lawyer.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **pension and fiduciary**: a register of **pension schemes** with **contributions** (exact totals, late and missing months), **funding valuations** (assets against liabilities, exact funding ratio), a **fiduciary calendar** of obligations and a **conflict-of-interest register**. Each item is recorded by one person and confirmed by a different person. **It holds no member data, calculates no benefit or contribution rate, values nothing itself and applies no pension or trust law.**

Screen: **Pension and fiduciary** (menu, under Professional workspaces). API prefix `/pension`. Stored in the shared document store (kinds `pen_scheme`, `pen_setting`). Reference numbers: PS- (schemes). Service methods are prefixed `pen_`.

## What it does
1. **Schemes.** A name, a reference code, a three-letter currency, a type (defined benefit, defined contribution, hybrid, other), the first contribution month, the day of the month contributions fall due (1 to 28) and a description. **Proposed by one person and approved or rejected by a different person.** Statuses: Waiting for a decision, Open, Rejected, Closed.
2. **Contributions.** A month, an employer amount, an employee amount (one may be zero, not both) and the date paid. A month's contribution is due on the due day of the **following** month; one paid after that is flagged late. One live contribution per month. **Recorded by one person, confirmed or rejected by a different person.** Employer, employee and combined totals are exact and cover only confirmed contributions. Months past their due date with no contribution recorded are listed as missing.
3. **Funding valuations.** An "as of" date, the assets, the liabilities (more than zero) and where the figures came from. **Recorded by one person, confirmed or rejected by a different person.** From the latest confirmed valuation the screen shows the funding ratio (assets divided by liabilities, two decimals, exact), the surplus or deficit, and flags a ratio below your floor or a valuation older than your limit.
4. **Fiduciary calendar.** A title and a due date. One person marks it done (a date and a note); a different person confirms it, or sends it back to open with a reason. Open obligations are flagged overdue or due soon.
5. **Conflict register.** A person reference code, the date declared and the nature of the interest. **Recorded by one person, reviewed by a different person.**
6. **Closing.** An approver closes an open scheme with a reason once nothing is waiting for a decision.
7. **Settings.** Funding floor (percent), days before a valuation is stale, days that count as due soon. These are your own settings, not rules.
8. **Overview.** Counts by status, contributions per currency (never added together) and a list of things to look at.

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`pension:prepare`: propose schemes, record contributions, valuations, obligations and declarations, mark obligations done): Owner, Administrator, Manager, Auditor.
- Approve (`pension:approve`: approve, reject or close schemes, confirm or reject records, change settings): Owner, Approver, Manager.
- The person who recorded an item can never be the one who decides it; this is enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not names, codes, amounts, notes or reasons.

## What it does NOT do
- It holds no member data and calculates no benefit, contribution rate or statutory funding test. Liabilities come from an actuary and are typed by people.
- It applies no pension or trust law. Due dates use the due day you set; real rules about when contributions are due, and the consequences of lateness, may differ. The calendar does not tell you which duties apply to you.
- Amounts, valuations and declarations are typed by people. A different person confirming them is a review of what was typed, not a check against bank, custodian or actuary records.
- Records cannot be edited after a decision; a correction is a new record that a person explains. Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_pension.py` (31 tests; funding ratios are checked against an independent exact calculation) plus the static route-security, audit-coverage, tenant-isolation, boundary and router-names tests; an odd-input run (1,050 calls) found and fixed one crash (an unhashable record kind), none remain.
- Frontend: `frontend/tests/pension.test.js` (17 tests).
- Browser: `e2e/journey_pension.py` (89 checks across Accountant, Administrator, Approver and Owner sign-ins).
