# Stage 33: Data governance

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a data-protection or information-security professional.

## What it is
A records workspace for the gap the Phase-1 audit listed as a missing workspace, **data governance**: a register of **data assets** (what data the organisation holds, who owns it, how it is classified, how long it is kept, whether it holds personal data), recorded **periodic reviews**, and **time-limited access grants**, each approved or confirmed by a different person. **It holds none of the data, enforces no access, scans nothing and applies no law (including no data-protection law).** It is a register that people keep honest, not an access-control or privacy-compliance system.

Screen: **Data governance** (menu, under Professional workspaces). API prefix `/datagov`. Stored in the shared document store (kinds `dg_asset`, `dg_setting`). Reference numbers: DA- (assets). Service methods are prefixed `dg_`.

## What it does
1. **Assets.** Name, an owner reference code (not a name), a classification (Public, Internal, Confidential, Restricted), whether it holds personal data, how long it is kept (1 to 1200 months), how often it is reviewed (1 to 60 months) and a description. **Proposed by one person and approved or rejected by a different person.** Statuses: Waiting for a decision, Approved, Rejected, Retired.
2. **Reviews.** On an approved asset, a person records a review (date not in the future, not before approval, plus an outcome). **A different person confirms or rejects it.** The next review is due the review interval after the latest confirmed review (or after approval); a review that is overdue is flagged.
3. **Access grants.** A reference for the person, read or write access, a purpose, a start and an expiry date. Access lasts at most three years, or one year on a Restricted asset; an expiry already in the past is refused; the same person at the same level cannot be proposed twice while a grant is live or waiting. **A different person approves or rejects it**, and an approver can revoke it later with a reason. States follow the dates: Not yet active, Active, Expiring soon (inside your own warning window), Expired, Revoked.
4. **Retiring.** An approver retires an approved asset with a reason, once no grant is waiting, active or approved-but-not-yet-started, and no review is waiting.
5. **Overview.** Counts by status and classification, assets holding personal data, active grants, percentage of reviews on time (two decimals), and a list of items for a person to look at.
6. **Flags (for a person to look at, never blocking).** Reviews overdue, grants expiring soon, and more active grants on a Restricted asset than your own limit.
7. **Settings (approver).** The expiry warning window (1 to 365 days, default 30) and the most active grants on a Restricted asset (1 to 1000, default 5).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`datagov:prepare`: propose assets, record reviews, propose grants): Owner, Administrator, Manager, Auditor.
- Approve (`datagov:approve`: approve, reject or retire assets, confirm or reject reviews, approve, reject or revoke grants, change the settings): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who proposed an item can never be the one who decides it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not names, owner or person references, purposes, outcomes or notes.

## What it does NOT do
- It holds none of the data and connects to no system. An approved grant is a recorded decision; **it does not give or remove anyone's access anywhere**, and nothing checks that real access matches the register.
- It scans nothing, discovers no data, classifies nothing automatically and applies no law or standard. Whether an asset really holds personal data, or is classified correctly, is whatever a person typed and another person approved.
- Approval by a different person is a review of what was typed, not a check against the real world.
- Assets cannot be edited after approval; a correction is a new asset. Retention periods are recorded, not enforced, and nothing deletes data.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_datagov.py` (25 tests, including exact month arithmetic, grant states on the boundary days and router guards) plus the static route-security, audit-coverage, tenant-isolation, boundary and new router-names tests; an odd-input run (992 calls) found no crashes.
- Frontend: `frontend/tests/datagov.test.js` (15 tests).
- Browser: `e2e/journey_datagov.py` (72 checks across Accountant, Administrator, Approver and Owner sign-ins).
- Defects found and fixed while testing: an approved grant that had not started yet did not block retiring the asset; the assets list route referenced an undefined `status` (caught by the journey, and a new test now guards every router against this).
