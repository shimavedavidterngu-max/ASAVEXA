# Stage 20: IT audit

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not independently reviewed by an IT-audit professional.

## What it is
A records-and-checks workspace for two things auditors do with an organisation's systems: **change-management testing** (were changes to a system approved, tested and reversible?) and **application-control testing** (does an application do what a control says it should?). **It does not connect to any system, does not read any ticket, and does not test any application.** It keeps what people typed in from their own change system, applies fixed rules to it, draws a repeatable sample, records who concluded what, and requires a different person to approve each test.

Screen: **IT audit** (menu, under Professional workspaces). API prefix `/itaudit`. Stored in the shared document store (kinds `ia_change`, `ia_control`, `ia_test`, `ia_setting`). Reference numbers: CH- (change), AC- (control), TS- (test). Methods are prefixed `ia_`. A change or a control can optionally link to a Cybersecurity asset of the same company; the link is checked and the name is kept.

## What it does
1. **Change records.** Typed in from the organisation's own change system: system, ticket number, title, what changed, type (standard, normal, emergency), risk, who asked, who approved and when (both or neither), go-live date (not in the future), testing evidence, rollback plan and optional Evidence Vault documents (file fingerprints kept). The same ticket cannot be recorded twice for the same system. Nothing is edited. A record entered in error is **voided** by a different approver with a reason, and then leaves later populations.
2. **Fixed flags.** Six rules over the typed facts: no approval recorded; approved after go-live (not for emergency changes); emergency change approved later than the allowed number of days; approved by the person who asked (names compared ignoring case); no testing evidence (not required for standard changes); no rollback plan on a medium or high risk change. The emergency window is a setting; each record keeps the window in force when it was recorded.
3. **Change-management tests.** The tester chooses a period of go-live dates, an optional system, a sample size, a seed (any words) and a tolerable number of exceptions. The sample is the changes whose hash with the seed sorts lowest, so **anyone with the seed, the period and the size gets the same sample**. A fingerprint of the whole population is kept. Each sampled change is snapshotted. The tester concludes each one: *no exception* or *exception*. A flagged change can be called *no exception* only with an explanation of at least 20 characters (counted as an override); an exception needs a note of at least 10.
4. **Application controls.** A control has a system, a name, a type, what it does, the expected result, how often it operates and a tolerable number of exceptions. A control is tested by recording **test cases** (what was tried, expected, actual, passed or failed, the date, optional documents); a failed case needs a note. A control can be retired by an approver, with a reason, when no test of it is in progress. A control is flagged when it has never been tested or when its last approved test is older than the retest interval (a setting).
5. **Two-person approval.** The tester submits; a different person approves or sends it back with a reason. The approver cannot be the tester, cannot have recorded any sampled change, and cannot have defined the control being tested. A test with exceptions or overridden flags needs a written approval note of at least 10 characters. The result is **within tolerance** or **above tolerance**: the exceptions found compared with the number your own test allowed. A sent-back test returns to the tester.
6. **Tester independence.** A tester cannot plan a change test whose sample includes changes they recorded (the refusal names them and uses up no reference number), and cannot plan a test of a control they defined.
7. **Withdrawing.** The person who planned a test that is still being worked on can withdraw it with a reason, which frees its changes and its control. A submitted or approved test cannot be withdrawn.
8. **Overview.** A "what needs attention" list (flagged changes not yet in a submitted or approved test, flagged emergency changes, tests waiting for approval, tests above tolerance, controls never tested, controls due for retest), counts, the settings and the limits.

## Who may do what
- View (`audit:read`, the same permission as Cybersecurity): everyone who holds it, including Reviewers, Auditors, External Auditors and Read-only members.
- Prepare (`itaudit:prepare`: record changes and controls, plan and conclude tests, add cases, submit, withdraw): Owner, Administrator, Manager, Auditor.
- Approve (`itaudit:approve`: approve or send back tests, void changes, retire controls, set the settings): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The separation rules are enforced by the service for every role, including the Owner. The audit trail records reference numbers and outcomes, not the text people typed.

## What it does NOT do
- It does not connect to a ticketing or change system, pull logs, scan or test any application, or check that what people typed is true.
- A flag is a rule applied to typed facts. It points at something to look at; it is not a finding and not a conclusion that a change was wrong.
- A sample is repeatable but **not statistical**. It supports no conclusion about every change.
- *Within tolerance* and *above tolerance* are arithmetic against your own number. They are not an audit opinion, assurance or evidence of compliance with any standard.
- It cannot know about a relationship nobody records (for example, a tester who is also the approver of a change under another name).
- It does not post to the ledger.
- Two people sending the same request at the same instant are not guaranteed to be caught by the duplicate checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Found and fixed while testing
- **Real defect, found while designing the browser journey and fixed:** a person who planned a change test and had also recorded one of the sampled changes could never finish it (they may not test their own records), and nothing could end the test, which would also block voiding its changes. Planning now refuses a sample that includes the planner's own records, and a planner can withdraw a draft test.
- **Real defect, found by a server test and fixed:** an optional note shorter than the minimum was accepted when it was left optional. A note, when given, now obeys its minimum length everywhere.
- Other failures in the first runs were mistakes in my own tests or journey: test dates later than the test clock, a call that read the test's status as if it were an HTTP code, and so many background sign-ins in one journey that the browser's own session was pushed out.

## Verification (test environment only)
- Server: `tests/test_itaudit.py` (39 tests: settings, flags, validation, duplicates, evidence and asset links, voiding, repeatable samples, population rules, tester and approver independence, tolerance arithmetic, approval notes, send-back, withdrawal, controls, retest, overview, company isolation, audit without content, role permissions, router guards) plus the static route-security, audit-coverage, boundary and entity checks.
- Frontend: `frontend/tests/itaudit.test.js` (19 tests: permissions, payload builders, which buttons each person sees, every tab for every role and person, client paths, menu wiring).
- Browser: `e2e/journey_itaudit.py` (75 checks across Accountant, Owner, Administrator and Approver sign-ins, including an accountant refused by the server, the server refusing what the buttons hide, a second company seeing nothing, and the audit actions). The test server gained one extra person (an Administrator) so that one person can record and a different person can test.
