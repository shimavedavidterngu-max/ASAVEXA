# Stage 24: Company secretarial

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a company secretary or lawyer.

## What it is
A records-and-checks workspace for the gap the Phase-1 audit listed as a missing workspace, **company secretarial**: **meetings with minutes**, **resolutions** and a **register of statutory filings**. **It checks no law and contacts no registry.** It keeps what people typed and enforces who may decide what.

Screen: **Company secretarial** (menu, under Professional workspaces). API prefix `/secretarial`. Stored in the shared document store (kinds `cs_meeting`, `cs_resolution`, `cs_filing`, `cs_setting`). Reference numbers: MT- (meeting), RS- (resolution), FL- (filing). Service methods are prefixed `cs_`. Evidence Vault documents can be attached to minutes and filings (file fingerprints kept).

## What it does
1. **Meetings.** Schedule a board, committee, annual general, general or other meeting (title, date within two years, location, agenda). On or after the meeting date, record who attended and the minutes (at least 20 characters). A **different person approves the minutes**. A meeting still scheduled can be cancelled with a reason, but not while resolutions put to it are waiting. A meeting past its date with no minutes is flagged.
2. **Resolutions.** Ordinary, special or written. An ordinary or special resolution is put to a meeting that is scheduled or held (not yet approved or cancelled); a written resolution is put to none. **A resolution put to a meeting can be decided only after minutes of that meeting exist.** A **different person from the proposer decides it**, recording votes for, against and abstentions (whole numbers, at least one) and the outcome with a note. It can be recorded as passed only if more votes were for than against. A proposed resolution can be withdrawn with a reason.
3. **Filings register.** A statutory obligation (annual return, accounts, change of directors, change of address, share change, tax return, licence renewal, other) with authority, due date and owner. It is flagged overdue after its due date and "due soon" within your window (default 14 days). Someone records it as filed (date not in the future, receipt or reference), and a **different person confirms it**. An open filing can be withdrawn with a reason.
4. **Overview.** "What needs attention": filings overdue, due soon, waiting for confirmation; meetings with no minutes; minutes waiting for approval; resolutions ready to decide. Counts, one setting (days before a filing is due soon, 1 to 90) and the limits.

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`secretarial:prepare`: schedule meetings, record minutes, propose resolutions, add filings, record as filed): Owner, Administrator, Manager, Auditor.
- Approve (`secretarial:approve`: approve minutes, cancel meetings, decide or withdraw resolutions, confirm or withdraw filings, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who recorded the minutes, proposed the resolution or recorded the filing as filed can never be the one who approves, decides or confirms it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not the text people typed.

## What it does NOT do
- It does not check company law, your articles of association, who may attend or vote, quorum or notice periods.
- A resolution passes here on a simple majority of recorded votes only. A higher threshold (for example for a special resolution) is not checked.
- A filing marked filed or confirmed is a person's statement. ASAVEXA does not contact any registry and cannot tell whether it was filed or accepted.
- Approved minutes are not a signed statutory record. Keep the signed originals in the Evidence Vault or wherever your law requires.
- It cannot know about a meeting, resolution or obligation nobody records.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_secretarial.py` (36 tests) plus the static route-security, audit-coverage and boundary tests.
- Frontend: `frontend/tests/secretarial.test.js` (14 tests).
- Browser: `e2e/journey_secretarial.py` (65 checks across Accountant, Owner, Administrator and Approver sign-ins).
