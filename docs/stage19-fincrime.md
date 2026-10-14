# Stage 19: Financial-crime casework

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not independently reviewed by a financial-crime or legal professional.

## What it is
A records-and-checks workspace for the chain **alert → case → conflict declarations → timeline → screening results → outcome decided by a different person → loss and recovery**. **It does not screen anyone against any list, does not monitor transactions, does not file a report with any authority, and an outcome is not a finding of guilt.** It keeps what people noticed, who looked, who declared a conflict, what they decided and who decided it.

Screen: **Financial-crime casework** (menu, under Professional workspaces). API prefix `/fincrime`. Stored in the shared document store (kinds `fc_alert`, `fc_case`, `fc_setting`). Reference numbers: AL-, CS-. It also covers the gaps the expansion audit found in the forensic workspace: conflict declarations, an incident timeline, and loss and recovery.

## What it does
1. **Alerts.** Raised with a source (transaction monitoring, screening hit, staff report, external tip, audit finding, other), a written summary, the date noticed (not in the future), an optional amount and currency, and optional Evidence Vault documents (file fingerprints kept). A **different person** must dismiss an alert, with a written reason of at least 10 characters.
2. **Cases.** Opened by a preparer, who becomes the **lead investigator**. A case can bring in waiting alerts or start without one. **The opener must declare a conflict of interest question first**; saying "yes" refuses the opening and nothing is created.
3. **Conflict-of-interest declarations.** Nobody works or decides a case until they have declared on that case. A person who declares a conflict is out: they cannot work or decide it, and **a declared conflict can never be withdrawn**. If the lead declares one, the case has no lead and is flagged until a decision-maker names a new one (who must have declared no conflict and be able to work cases). A declaration can be made on a closed case, because a decision-maker must declare before reopening it.
4. **Timeline.** The lead adds dated events (transaction, contact, document, observation, other) with optional documents. Events only accumulate; none is edited or deleted.
5. **Screening results.** Typed in by the lead: who or what was screened, the kind of check, the list or source they say they used, the date and the result. A **possible match** must be resolved (not a match / confirmed) by a different, cleared decision-maker with a written reason before any outcome can be proposed or approved. A confirmed match (or a possible match resolved as confirmed) blocks a "no concern" outcome.
6. **Losses and recoveries.** Exact two-place amounts per currency; currencies are never added or converted. A recovery needs a loss in the same currency, cannot exceed the loss, and counts only once a **different** cleared decision-maker confirms it. A rejected recovery frees its room.
7. **Outcomes.** The lead proposes one of: no concern, concern found and resolved, or refer onward (naming to whom, as text). A different person decides it: **not the lead, not the person who opened the case, not the person who proposed it, and not anyone who raised an alert that is part of the case**, and they must have declared no conflict. They approve (the case closes) or send it back with a reason. A closed case can be reopened by a cleared decision-maker with a reason; the earlier decision stays in the history.
8. **Targets** (decision-makers only): days before an unlooked-at alert is flagged and before an open case is flagged. These are your own targets, not a legal deadline.
9. **Overview.** A "what needs attention" list: alerts waiting, cases with no lead, outcomes waiting for a decision, unresolved screening matches, recoveries to confirm, ageing cases; plus counts and open cases by severity.

## Who may do what
Cases are confidential, so the permissions follow the forensic workspace, **not** the everyday `reporting:read`:
- View (`fincrime:read`): Owner, Approver, Manager, Auditor. Accountants, Finance Officers, Administrators, Reviewers, External Auditors and Read-only members cannot see alerts or cases at all.
- Prepare (`fincrime:prepare`: raise alerts, open and work cases, record screening results, losses, recoveries, propose outcomes): Owner, Auditor.
- Decide (`fincrime:approve`: dismiss alerts, resolve matches, confirm or reject recoveries, decide outcomes, change the lead, reopen, set targets): Owner, Approver, Manager.
- Anyone who can prepare or decide can also view. Declaring a conflict needs only `fincrime:read`.
- Separation is enforced by the service for every role, including the Owner. The content of a case is not copied into the audit trail, which records only reference numbers and outcomes.

## What it does NOT do
- It does not screen anyone against sanctions, politically-exposed-person or other lists, monitor transactions, verify a supplier or customer, or connect to any outside system.
- It does not file a suspicious-activity or any other report. "Refer onward" records only that people decided a referral should be made, to whom they say, and who decided it.
- An outcome is a record of a decision. It is not a finding of guilt, legal advice, an audit opinion or evidence of regulatory compliance.
- It cannot know about a conflict that nobody declares.
- It does not post to the ledger.
- Two people sending the same request at the same instant are not guaranteed to be caught by the duplicate checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Found and fixed while testing
- **Real defect, found by a server test and fixed:** a decision-maker could not declare "no conflict" on a **closed** case, so nobody could ever reopen one. Declarations are now allowed on a closed case (a declared conflict still blocks reopening).
- **Real defect, found by the browser journey and fixed:** a decision-maker who could resolve a screening match or reject a recovery had no box to type the required reason into (the box only appeared once an outcome had been proposed). One shared reason box now appears whenever the person could decide something on the case, and a frontend test pins it.
- Other failures in the first runs were mistakes in my own tests or journey: a "future" date of tomorrow that the one-day UTC leeway correctly allowed, a note given for a "no conflict" declaration that was shorter than the 10-character minimum for any note, and a case panel the page deliberately remembers between visits being toggled closed by a second click.

## Verification (test environment only)
- Server: `tests/test_fincrime.py` (42 tests: policy, alerts, case opening, declarations, lead changes, timeline, screening, loss and recovery arithmetic, outcome rules, overview, company isolation, audit and confidentiality, role permissions, router guards) plus the static route-security and audit-coverage checks.
- Frontend: `frontend/tests/fincrime.test.js` (28 tests: permissions, payload builders, which buttons each person sees, every tab for every role and person with and without an open case, client paths, menu wiring).
- Browser: `e2e/journey_fincrime.py` (52 checks across Accountant, Owner and Approver sign-ins, including an accountant refused by the server, the server refusing what the buttons hide, a second company seeing nothing, and the audit actions).
