# Stage 25: Fixed assets

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by an accountant.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **fixed assets**: a **register of assets**, a **straight-line depreciation schedule**, **disposals** and **physical counts**. **It posts nothing to the ledger and follows no accounting standard or tax rule.** It keeps what people typed, does exact decimal arithmetic on the typed figures, and enforces who may decide what.

Screen: **Fixed assets** (menu, under Professional workspaces). API prefix `/fixedassets`. Stored in the shared document store (kinds `fa_asset`, `fa_setting`). Reference numbers: FA-. Service methods are prefixed `fa_`. Evidence Vault documents can be attached to assets and counts (file fingerprints kept).

## What it does
1. **Assets.** Name, category (land, buildings, plant and machinery, vehicles, furniture and fittings, IT equipment, other), location, custodian, acquisition date (not in the future), currency (three letters), cost (more than zero), residual value (less than cost), useful life in months (1 to 600) and an optional serial number. Amounts are written as text such as 1500.00 with at most two decimals; floating-point numbers are refused. **Land is recorded without depreciation** (no life, no residual value). A different person approves or rejects (rejection needs a reason). A serial number already used by a proposed, active or pending-disposal asset is refused.
2. **Depreciation.** Straight line, in whole months from the acquisition date (a month is complete on the same day of the month): depreciation so far = (cost minus residual) x months / life, rounded to two decimals, never more than cost minus residual. Net book value = cost minus that. A month-by-month schedule for the next months is shown. Everything is exact decimal arithmetic on the typed figures.
3. **Disposals.** For an active asset: date (not future, not before acquisition), proceeds (zero allowed) and a reason. The net book value at the disposal date and the difference to the proceeds are worked out and kept. A **different person approves or rejects** (rejection needs a reason and the asset stays active). Once disposed of, the figures are frozen at the disposal date.
4. **Physical counts.** For an active asset: date (not future), result (found, missing, damaged) and a note. A **different person reviews** each count. An active asset whose latest count says missing is flagged; one not counted within your window (default 365 days, 30 to 730) is flagged.
5. **Overview.** "What needs attention": missing assets, counts overdue, assets and disposals waiting for approval, counts to review. Totals of cost, depreciation and net book value for active assets **per currency**, counts, the setting and the limits.

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`fixedassets:prepare`: propose assets and disposals, record counts): Owner, Administrator, Manager, Auditor.
- Approve (`fixedassets:approve`: approve or reject assets and disposals, review counts, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who proposed an asset or a disposal, or recorded a count, can never be the one who approves or reviews it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not the typed text or amounts.

## What it does NOT do
- It posts no journal entry, does not value or revalue anything, and does not check the figures against invoices.
- Net book value and the gain or loss on disposal are arithmetic on typed figures, not an accounting or tax result. Only straight-line depreciation is supported. Impairment, component accounting, part-month conventions other than whole months, and tax allowances are not handled.
- A count is a person's statement. ASAVEXA cannot tell whether an asset exists.
- Amounts in different currencies are never added together.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_fixedassets.py` (34 tests) plus the static route-security, audit-coverage and boundary tests.
- Frontend: `frontend/tests/fixedassets.test.js` (13 tests).
- Browser: `e2e/journey_fixedassets.py` (65 checks across Accountant, Owner, Administrator and Approver sign-ins, comparing the page with the exact arithmetic).
