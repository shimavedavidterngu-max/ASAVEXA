# Stage 22: AI governance

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by an AI-governance, legal or risk professional.

## What it is
A records-and-checks workspace for the AI-governance gap the Phase-1 audit listed as Partial: an **inventory of AI systems with intended use**, **model changes** and an **AI incident log**. **It connects to no AI system, tests nothing and measures no output.** It keeps what people typed and makes a different person approve, review or decide each record.

Screen: **AI governance** (menu, under Professional workspaces). API prefix `/aigov`. Stored in the shared document store (kinds `aig_system`, `aig_change`, `aig_incident`, `aig_setting`). Reference numbers: AI- (system), MC- (model change), AX- (incident). Service methods are prefixed `aig_`. Evidence Vault documents can be attached (file fingerprints kept).

## What it does
1. **AI systems.** Name, what it does, where it comes from (in-house, vendor, open source; a vendor or project name is required unless in-house), **intended use**, **uses that are not allowed**, a **risk tier** (minimal, limited, high: your own label), owner, optional kinds of data used, and how a person oversees it (required for the high tier). A different person approves or rejects (rejection needs a reason). **The intended use, the not-allowed uses and the tier cannot be changed once approved**; to change them, retire the system and propose a new one. A duplicate name among proposed or approved systems is refused.
2. **Reviews.** A different person from the proposer records a periodic review of an approved system (note of at least 10 characters). A system not reviewed (or, if never reviewed, approved) within your interval (default 180 days) is flagged as due.
3. **Model changes.** Recorded against an approved system: kind (model update, prompt change, data change, settings change, vendor change), version before and after (must differ), what changed, date (not in the future), how it was tested. **A change to a high-tier system needs a linked test document.** A different person approves, or rejects with a reason. The tier at the time of the change is kept. A system cannot be retired while a change waits.
4. **Incidents.** Recorded against an approved or retired system: kind, severity (low to critical), what happened, dates (found not before it happened; not in the future), harm (required for high and critical), optional people affected. A different person reviews it (cause at least 10 characters, corrective action at least 20) or voids it with a reason while unreviewed. An unreviewed incident is flagged overdue after your window (default 7 days). A system cannot be retired while an incident is unreviewed.
5. **Overview.** "What needs attention": severe incidents unreviewed, incidents overdue, systems due for review, systems/changes/incidents waiting for a different person; counts by tier; two settings (review interval 30 to 730 days, incident window 1 to 60 days); the limits.

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`aigov:prepare`: propose systems, record changes and incidents): Owner, Administrator, Manager, Auditor.
- Approve (`aigov:approve`: approve, reject, retire, review systems; approve or reject changes; review or void incidents; set the settings): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who proposed or recorded a record can never be the one who approves, reviews or decides it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not the text people typed.

## What it does NOT do
- It does not connect to, test, monitor or measure any AI system, or check that what people typed is true.
- The risk tier is your own label. It is not a legal classification under any law or standard and not an assessment of how risky the system is.
- A change record shows who said what changed and who approved it; it does not show the change was tested well or was the only change.
- It cannot know about a system, change or incident nobody records.
- It does not claim compliance with any AI regulation or standard.
- Two people sending the same request at the same instant are not guaranteed to be caught by the duplicate checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Found and fixed while testing
- Carrying forward the Stage 21 lesson (badges joined to text showing "[object Object]"), the page places badges as elements from the start and a frontend test pins it.
- Failures in the first runs, if any, are listed in the Project report; no product defect was found by the server tests on the first run.

## Verification (test environment only)
- Server: `tests/test_aigov.py` (29 tests: settings, systems, reviews, changes, incidents, overview, company isolation, audit without content, role permissions, router guards) plus the static route-security, audit-coverage and boundary tests.
- Frontend: `frontend/tests/aigov.test.js` (14 tests). Whole frontend suite: 1081 passing.
- Browser: `e2e/journey_aigov.py` (about 67 checks across Accountant, Owner, Administrator and Approver sign-ins).
