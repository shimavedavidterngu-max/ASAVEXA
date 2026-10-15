# Stage 31: Payroll and workforce cost

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a payroll, employment-law or tax professional.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **payroll and workforce cost**: **payroll runs** made of **pay lines that people type in**, added up exactly, **submitted by one person and approved or returned by a different person**. **It calculates no tax, pension or other statutory amount, pays nobody, moves no money, files nothing and holds no names, bank details or national identifiers. It is not a payroll system.**

Screen: **Payroll and workforce cost** (menu, under Professional workspaces). API prefix `/payroll`. Stored in the shared document store (kinds `pw_run`, `pw_setting`). Reference numbers: PR- (runs). Service methods are prefixed `pw_`.

## What it does
1. **Runs.** A label, a pay period (end not before start, at most 366 days, end not in the future) and a three-letter currency. Statuses: Draft, Waiting for review, Approved, Returned, Withdrawn.
2. **Pay lines.** A staff reference code (not a name; unique among active lines in the run, case-insensitive), a department, base pay, optional allowances, up to 8 typed deductions (label and amount) and optional employer contributions. **Gross = base pay + allowances; net = gross - deductions; cost to the employer = gross + employer contributions.** Deductions cannot exceed gross. Money is exact decimals, at most two decimals, ASCII digits, commas only as thousands separators; floats are refused. A run holds at most 500 lines. A wrong line is removed with a reason (kept) and entered again.
3. **Review.** A draft or returned run is submitted (needs at least one active line). **A different person approves it, or returns it with a reason**; the preparer can edit a returned run and submit again, or withdraw it with a reason.
4. **Totals.** Per run and per department, and for approved runs per currency. **Amounts in different currencies are never added together.** Only approved runs are totalled.
5. **Flags (for a person to look at, never blocking).** Overlapping pay (the same staff reference active in another submitted or approved run, same currency, overlapping period; drafts are not compared) and lines above a review limit on gross pay (your own setting; 0 turns it off).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`payroll:prepare`: start runs, add and remove lines, submit, withdraw): Owner, Administrator, Manager, Auditor.
- Approve (`payroll:approve`: approve or return runs, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who submitted a run can never be the one who decides it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not staff references, amounts, labels or notes.

## What it does NOT do
- No income tax, pension, social insurance, levy or any statutory calculation. Deductions are amounts a person typed; ASAVEXA does not know whether they are right or lawful.
- It pays nobody and connects to no bank, payment service or tax authority. An "approved" run is a recorded internal review, not an instruction to pay.
- Staff are identified only by a reference code you choose. Keep names, bank details and identifiers out of every field.
- Approval by a different person is a review of what was typed, not a check against contracts, timesheets or the real world.
- Overlap and limit flags are prompts, not controls. Leave, hours, overtime, payslips and year-end filings are out of scope.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_payroll.py` (25 tests; exact figures checked against an independent fraction-based calculation) plus the static route-security, audit-coverage, tenant-isolation and boundary tests; an odd-input run (450 calls) found no crashes.
- Frontend: `frontend/tests/payroll.test.js` (14 tests).
- Browser: `e2e/journey_payroll.py` (Accountant, Administrator, Approver and Owner sign-ins, comparing the page with exact figures).
