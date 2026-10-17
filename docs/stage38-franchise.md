# Stage 38: Franchise and multi-location

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a franchise lawyer.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **franchise and multi-location**: a register of franchised outlets or branches, each with a **royalty rate**, **monthly sales reports** and **royalty payments**. Reports and payments are each recorded by one person and confirmed by a different person, and the royalty due, the amount paid and the balance are **worked out exactly**, per location and per currency. **It reads no franchise agreement, collects no money, audits no sales and applies no franchise law.**

Screen: **Franchise and multi-location** (menu, under Professional workspaces). API prefix `/franchise`. Stored in the shared document store (kinds `fch_location`, `fch_setting`). Reference numbers: FL- (locations). Service methods are prefixed `fch_`.

## What it does
1. **Locations.** A name, a reference code, a three-letter currency, a royalty rate in percent (up to two decimals, more than zero, at most 100), the day of the month reports fall due (1 to 28), the first reporting month and a description. **Proposed by one person and approved or rejected by a different person.** Statuses: Waiting for a decision, Open, Rejected, Closed.
2. **Sales reports.** A month, the gross sales (zero is allowed) and the date submitted. Due on the due day of the following month; one submitted after that plus the grace days is flagged late. One live report per month. **Recorded by one person, confirmed or rejected by a different person.** The royalty for a report is gross sales times the rate, exactly, rounded to two decimals half away from zero. Months past due with no report are listed as missing.
3. **Royalty payments.** An amount (more than zero), the date and a note. **Recorded by one person, confirmed or rejected by a different person.**
4. **Balance, exact.** Royalty due is the sum over confirmed reports; paid is the sum of confirmed payments; the balance is royalty due less paid (negative means overpaid). The overdue amount is the royalty of confirmed reports whose due date plus grace days has passed, less confirmed payments, never below zero.
5. **Closing.** An approver closes an open location with a reason once nothing is waiting for a decision.
6. **Setting.** The grace period in days (0 to 60). It is your own setting, not a rule.
7. **Overview.** Counts by status, totals per currency (never added together) and a list of things to look at (locations and items waiting, missing and late reports, overdue royalty, overpayments).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`franchise:prepare`: propose locations, record sales reports and payments): Owner, Administrator, Manager, Auditor.
- Approve (`franchise:approve`: approve, reject or close locations, confirm or reject records, change the setting): Owner, Approver, Manager.
- The person who recorded an item can never be the one who decides it; this is enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not names, codes, amounts, notes or reasons.

## What it does NOT do
- It reads no franchise agreement, collects no money, connects to no bank or till system and audits no sales. The rate, sales and payments are typed by people.
- It applies no franchise, consumer or tax law. Tiered or minimum royalties, fees, deductions, interest, penalties and set-off between locations are not calculated. Currencies are never added together.
- A different person confirming a record is a review of what was typed, not a check against till records or bank statements.
- Records cannot be edited after a decision; a correction is a new record that a person explains. Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_franchise.py` (25 tests; royalties are checked against an independent exact calculation, including half-cent rounding) plus the static route-security, audit-coverage, tenant-isolation, boundary and router-names tests; an odd-input run (736 calls) found no crashes.
- Frontend: `frontend/tests/franchise.test.js` (15 tests).
- Browser: `e2e/journey_franchise.py` (79 checks across Accountant, Administrator, Approver and Owner sign-ins).
