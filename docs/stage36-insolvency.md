# Stage 36: Insolvency

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by an insolvency practitioner or lawyer.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **insolvency**: a **case** for an insolvent estate, **creditor claims** that one person lodges and a different person admits or rejects, **realisations** (money in) and **costs** of the administration that one person records and a different person confirms, and an **illustrative distribution worked out exactly**, class by class in the order the case records, with every cent allocated. **It pays no one, files nothing with any court or office, and applies no insolvency law. The order in which the classes are paid is typed by a person and approved by a different person.**

Screen: **Insolvency** (menu, under Professional workspaces). API prefix `/insolvency`. Stored in the shared document store (kinds `isv_case`, `isv_setting`). Reference numbers: IC- (cases). Service methods are prefixed `isv_`.

## What it does
1. **Cases.** A title, a three-letter currency, a description, an optional claims deadline and the order the four classes are paid (Secured, Preferential, Unsecured, Subordinated; default in that order). **Proposed by one person and approved or rejected by a different person.** Statuses: Waiting for a decision, Open, Rejected, Closed.
2. **Claims.** A creditor reference code, a class, the amount claimed and the basis. **Lodged by one person and admitted (for an amount up to the claim, more than zero) or rejected (with a reason) by a different person.** A claim lodged after the deadline is flagged as late, not refused.
3. **Realisations and costs.** An amount, a date (not in the future) and a description. **Recorded by one person and confirmed or rejected by a different person.** Only confirmed entries count.
4. **The distribution, exact.** Available = confirmed realisations less confirmed costs less what earlier distributions already recorded (never below zero). It is applied class by class in the case's order to what each admitted claim is still owed. Inside a class the money is shared in proportion to what is still owed, **in whole cents with every cent allocated** (largest remainder, ties to the lower claim number), so the dividends always add up to the amount paid and no claim is paid more than it is owed. Per class and in total: owed, paid, recovery percentage (two decimals), shortfall and what is left over.
5. **Recording a distribution.** An approver who did not propose the case saves the calculation, once every lodged claim and proposed entry has been decided and there is something to distribute. This updates what each claim has been paid and what it is still owed; a later distribution pays only what is still owed. Several distributions can be recorded.
6. **Closing.** An approver closes an open case with a reason once nothing is waiting. A closed case takes nothing more.
7. **Overview.** Counts by status, totals per currency (never added together) and a list of items for a person to look at (cases and claims and entries waiting, late claims, costs above realisations, funds ready for a distribution).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`insolvency:prepare`: propose cases, lodge claims, record realisations and costs): Owner, Administrator, Manager, Auditor.
- Approve (`insolvency:approve`: approve, reject or close cases, admit or reject claims, confirm or reject entries, record a distribution): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who proposed an item can never be the one who decides it, and the person who proposed a case can never record its distribution; this is enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not titles, creditor references, amounts, descriptions or notes.

## What it does NOT do
- It pays no one and connects to no bank, court or registry. A recorded distribution is a calculation saved with its date; people outside ASAVEXA must pay and inform.
- It applies no insolvency law or ranking rule. The order of the classes is whatever was typed and approved and may not match the law that applies. No set-off, interest, tax, retention of title, charge, employee protection or costs-priority rule is applied. Secured creditors are paid from the same pool as others in their class.
- Claims, realisations and costs are typed by people. A different person admitting or confirming them is a review of what was typed, not a check against documents.
- A claim admitted after a distribution is paid only from later funds; earlier payments are not equalised. Surplus after every admitted claim is paid is shown as left over and not distributed.
- Claims and entries cannot be edited after a decision; a correction is a new claim or entry that a person explains. Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_insolvency.py` (31 tests; the share-out of every cent is checked against a separately written integer calculation over 500 random cases, and a worked estate with an odd-cent claim is checked line by line) plus the static route-security, audit-coverage, tenant-isolation, boundary and router-names tests; an odd-input run (868 calls) found no crashes.
- Frontend: `frontend/tests/insolvency.test.js` (14 tests).
- Browser: `e2e/journey_insolvency.py` (72 checks across Accountant, Administrator, Approver and Owner sign-ins, comparing every displayed dividend with an independent calculation).
