# Stage 23: Quality management

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a quality-management professional.

## What it is
A records-and-checks workspace for the gap the Phase-1 audit listed as missing item 11, **quality management and corrective actions**: a log of **nonconformances** (things that did not meet a requirement) and the **corrective and preventive actions** taken, each checked by a different person to see whether it worked. **It inspects nothing and measures nothing.** It keeps what people typed and enforces who may decide what.

Screen: **Quality management** (menu, under Professional workspaces). API prefix `/quality`. Stored in the shared document store (kinds `ql_nc`, `ql_action`, `ql_setting`). Reference numbers: NC- (nonconformance), CA- (action). Service methods are prefixed `ql_`. Evidence Vault documents can be attached (file fingerprints kept).

## What it does
1. **Raise.** Title, what was found, source (internal audit, customer complaint, process check, supplier, incident, other), severity (minor, major, critical), area or process, date it happened and date it was found (found not before it happened; neither in the future).
2. **Analyse.** Root cause (at least 20 characters) and what was done straight away to contain it (at least 10). Done once.
3. **Actions.** Only against an analysed nonconformance: corrective (fixes this problem) or preventive (stops it happening elsewhere), owner, due date (not before it was found, within two years). Marked completed with a date (not future) and a note; a **different person** then records whether it was effective or not effective (note of at least 20 characters). An open action can be cancelled with a reason.
4. **Close.** A different person from the one who raised it closes it, with a note. A nonconformance with live actions cannot close while any is open or waiting for a check, and needs a verified-effective action that is newer than any not-effective one. A **minor** one with no actions may close only with a stated reason (at least 20 characters). A nonconformance still not analysed can be voided by a different person, with a reason.
5. **Overview.** "What needs attention": critical open, overdue actions, overdue effectiveness checks, not-effective actions, actions waiting for a check, nonconformances to analyse, without any action, or ready to close; counts; one setting (days allowed for an effectiveness check, 7 to 180, default 30).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`quality:prepare`: raise, analyse, add and complete actions): Owner, Administrator, Manager, Auditor.
- Approve (`quality:approve`: verify or cancel actions, close or void nonconformances, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The separation rules (raiser cannot close or void; completer cannot verify) are enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not the text people typed.

## What it does NOT do
- It does not inspect, test or measure anything, or check that what people typed is true.
- "Effective" is a person's statement. Closing a record here is not a certification and does not show compliance with ISO 9001 or any other standard.
- It cannot know about a problem nobody records.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Found and fixed while testing
- Badges are placed as elements, never joined into text (the Stage 21 lesson); a frontend test pins it.
- Details of anything else found are in the Project report.

## Verification (test environment only)
- Server: `tests/test_quality.py` (32 tests) plus the static route-security, audit-coverage and boundary tests.
- Frontend: `frontend/tests/quality.test.js` (13 tests).
- Browser: `e2e/journey_quality.py` (59 checks across Accountant, Owner, Administrator and Approver sign-ins).
