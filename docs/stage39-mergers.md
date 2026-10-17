# Stage 39: Mergers and acquisitions

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a corporate lawyer.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **mergers and acquisitions**: a register of deals, each with a **due-diligence checklist**, **closing conditions** and **price adjustments**. Checklist items and conditions are marked done by one person and confirmed by a different person; adjustments are recorded by one person and confirmed by a different person. The **adjusted price** and the checklist progress are worked out exactly. **It values nothing, reads no contract and gives no deal, tax or legal advice.**

Screen: **Mergers and acquisitions** (menu, under Professional workspaces). API prefix `/mergers`. Stored in the shared document store (kinds `ma_deal`, `ma_setting`). Reference numbers: MD- (deals). Service methods are prefixed `ma_`.

## What it does
1. **Deals.** A name (a codename), a reference code, a three-letter currency, a type (acquisition, merger, disposal, other), a base price (more than zero), a target closing date and a description. **Proposed by one person and approved or rejected by a different person.** Statuses: Waiting for a decision, Open, Rejected, Closed (as completed or abandoned).
2. **Due-diligence checklist.** An item has a title and an area (financial, legal, tax, commercial, operational, other). One person marks it as provided (a date and a note); a different person confirms it, or sends it back to open with a reason. Progress is confirmed items over all items, exactly (two decimals), overall and per area.
3. **Closing conditions.** A title and a due date, handled the same way. Open conditions are flagged overdue or due soon (your own setting).
4. **Price adjustments.** An increase or a decrease, an amount (more than zero) and the basis. **Recorded by one person, confirmed or rejected by a different person.** The adjusted price is the base price plus confirmed increases less confirmed decreases, with the change and its percentage of the base price, all exact. A decrease that would take the price below zero cannot be confirmed.
5. **Closing.** An approver closes an open deal as **completed** or **abandoned**, with a reason, once nothing is waiting for a decision. Completed also needs every checklist item and condition confirmed.
6. **Setting.** The days that count as due soon (1 to 365). It is your own setting, not a rule.
7. **Overview.** Counts by status and outcome, open deals per currency (never added together) and a list of things to look at (deals and items waiting, open checklist items, overdue and due-soon conditions, deals past their target date).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`mergers:prepare`: propose deals, add checklist items, conditions and adjustments, mark items as provided or met): Owner, Administrator, Manager, Auditor.
- Approve (`mergers:approve`: approve, reject or close deals, confirm or reject records, change the setting): Owner, Approver, Manager.
- The person who recorded or marked an item can never be the one who decides it; this is enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not names, codes, amounts, notes or reasons.

## What it does NOT do
- It values nothing, reads no contract and gives no deal, tax or legal advice. Prices, adjustments, checklist items and conditions are typed by people.
- Completion accounts, earn-outs, escrow, currency terms and taxes are not applied. A checklist at 100 percent shows that every item typed was confirmed, not that the due diligence was complete.
- A different person confirming a record is a review of what was typed, not a check against documents or the other party.
- Records cannot be edited after a decision; a correction is a new record that a person explains. Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_mergers.py` (26 tests; the percentage change is checked against an independent exact calculation) plus the static route-security, audit-coverage, tenant-isolation, boundary and router-names tests; an odd-input run (928 calls) found no crashes.
- Frontend: `frontend/tests/mergers.test.js` (14 tests). Writing it found a real wiring defect (the screen called the close method with the wrong arguments), which is fixed.
- Browser: `e2e/journey_mergers.py` (86 checks across Accountant, Administrator, Approver and Owner sign-ins).
