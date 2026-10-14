# Stage 21: Risk indicators and resilience

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a risk or business-continuity professional.

## What it is
A records-and-checks workspace for the enterprise-risk gaps the Phase-1 audit listed under governance, risk and compliance: **key risk indicators** (KRIs), **loss events and near misses**, **business impact analysis** (recovery objectives per business process) and **continuity tests**. **It measures nothing and connects to no system.** It keeps what people typed, applies fixed arithmetic to it, and makes a different person confirm, review or approve each record.

Screen: **Risk indicators and resilience** (menu, under Professional workspaces). API prefix `/resilience`. Stored in the shared document store. Reference numbers: KR- (indicator), LE- (loss event), BP- (process), DR- (continuity test). Service methods are prefixed `rs_`. Records can optionally link to a risk from the Risk register (the link is checked and the title kept) and to Evidence Vault documents (file fingerprints kept).

## What it does
1. **Indicators.** Name, unit, direction (higher or lower is worse), amber and red thresholds (up to 4 decimals; amber and red must be in the right order for the direction), owner, how often a reading is expected. A different person approves or rejects (rejection needs a reason). **Thresholds cannot be changed once approved**; to change them, retire and propose a new one, so a threshold cannot be moved after seeing a bad number. A duplicate name among proposed or active indicators is refused.
2. **Readings.** Recorded against an active indicator (value, date not in the future, one non-rejected reading per date). A reading in the amber or red zone needs a note of at least 10 characters; an optional note still obeys its minimum. A different person confirms or rejects (with a reason). Only confirmed readings count: the latest confirmed reading gives the rating (green, amber, red) and an indicator with no confirmed reading inside its review period is **stale**. An indicator cannot be retired while a reading waits.
3. **Loss events and near misses.** A loss has an amount (2 decimals, positive) and a currency; a near miss must have neither. Found-on cannot be before happened-on; dates cannot be in the future. A different person reviews it (cause at least 10 characters, what was learned at least 20) or voids it with a reason while it is unreviewed. Totals are **per currency and never added across currencies**; voided records and near misses are excluded. A record not reviewed within the set number of days is flagged.
4. **Business processes.** Recovery time objective (1 to 8760 hours), recovery point objective (0 to 8760 hours), financial, legal and reputation impact; criticality is the highest of the three. A different person approves. **Objectives cannot be changed once approved.** A process cannot be retired while a test is waiting.
5. **Continuity tests.** Only against an approved process. The process's objectives are copied into the test when it is recorded. The test is **met** if recovery time is within the objective and lost work is within the recovery point objective, otherwise **not met**, and then a follow-up of at least 10 characters is required. A different person approves (a note of at least 10 characters is required to approve a missed test) or rejects with a reason. A process not tested within the set number of days (default 365) is flagged; one never tested is flagged separately.
6. **Overview.** A "what needs attention" list (red and amber indicators, stale indicators, readings to confirm, proposals to approve, loss reviews overdue, processes never tested, tests due, tests not met, tests to approve), counts, loss totals per currency, two settings (test interval 30 to 1095 days; loss review period 1 to 90 days) and the limits.

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`resilience:prepare`: propose indicators and processes, record readings, losses and tests): Owner, Administrator, Manager, Auditor.
- Approve (`resilience:approve`: approve, reject, confirm, review, void, retire, change the settings): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. **The person who proposed, recorded or carried out a record can never be the one who approves, confirms or reviews it**, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not the text people typed.

## What it does NOT do
- It does not connect to any system, take any measurement, or check that what people typed is true.
- A rating is arithmetic against thresholds you chose. It is not an assessment of how safe the organisation is.
- *Met* and *not met* compare numbers someone typed with objectives someone typed. They are not evidence that recovery would work in a real incident, and not compliance with any standard.
- Loss totals are only as complete as the records entered. They are not a loss database, a capital figure or a forecast.
- It does not post to the ledger, notify anyone, or run tests.
- Two people sending the same request at the same instant are not guaranteed to be caught by the duplicate checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Found and fixed while testing
- **Real defect, found by the frontend tests and fixed:** the "Review overdue", "Reading overdue", "No confirmed reading", "Test due" and "Never tested" badges were joined to text as a string, so the screen showed "[object Object]" instead of the badge. They are now placed as elements.
- Other failures in the first runs were mistakes in my own tests: a helper that confirmed the wrong reading because readings are sorted by date, a wrong expected count, an arithmetic slip in an expected loss total, a wrong assumption that a loss's age counts from the day it happened (it counts from the day it was recorded), and reading the returned indicator's status as if it were a reading's. One browser check was removed because the test stand-in server ignores the HTTP verb on a path; the real router has no such route.

## Verification (test environment only)
- Server: `tests/test_resilience.py` (43 tests: helpers, settings, indicators, readings, losses, processes, tests, overview, company isolation, audit without content, role permissions, router guards) plus the static route-security, audit-coverage and boundary tests.
- Frontend: `frontend/tests/resilience.test.js` (17 tests: permissions, payload builders, which buttons each person sees, every tab for every role and person, client paths, menu wiring). Whole frontend suite: 1067 passing.
- Browser: `e2e/journey_resilience.py` (about 96 checks across Accountant, Owner, Administrator and Approver sign-ins, including the server refusing what the buttons hide, own-work refusals, a missed objective needing a follow-up and an approval note, a second company seeing nothing, and the audit actions).
