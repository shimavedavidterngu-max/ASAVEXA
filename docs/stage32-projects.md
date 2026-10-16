# Stage 32: Projects and grants

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a grants or programme-finance professional.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **projects and grants**: a **project** with a **typed award**, currency, period and **budget lines**, approved by a different person; **spending and funder receipts** proposed by one person and decided by another; and **budget, spent, remaining, received and still-to-receive worked out exactly**. **It moves no money, applies no funder or donor rules and checks no eligibility. It is not a grant-management or compliance system.** (The older Public finance workspace has its own grant register for public bodies; this one is a separate, general project tracker.)

Screen: **Projects and grants** (menu, under Professional workspaces). API prefix `/projects`. Stored in the shared document store (kinds `pj_project`, `pj_setting`). Reference numbers: PJ- (projects). Service methods are prefixed `pj_`.

## What it does
1. **Projects.** Title, a funder reference code (not a name), a three-letter currency, an award (more than zero), and a period (end not before start, at most ten years). Statuses: Draft, Waiting for review, Open, Returned, Closed, Withdrawn.
2. **Budget lines.** A category (unique among lines in use) and an amount. **The lines can never add up to more than the award**; any difference is shown as unallocated. A wrong line is removed with a reason (kept) and entered again. At most 50 lines.
3. **Review.** A draft or returned project is submitted (needs at least one budget line). **A different person approves it, or returns it with a reason.** Only an approved (open) project accepts entries.
4. **Entries.** An entry is an **expense** against a budget line or a **receipt** (money from the funder), with an amount, a date inside the project period and not in the future, and a description. **Proposed by one person, approved or rejected by a different person** (rejection needs a reason). Only approved entries count. At most 2000 entries.
5. **Closing.** An approver closes an open project with a note, once every proposed entry has been decided. A closed project accepts nothing more.
6. **Totals.** Per project and per budget line: budget, spent, remaining, received, still to receive and percent spent (two decimals). Per currency across open and closed projects. **Amounts in different currencies are never added together.**
7. **Flags (for a person to look at, never blocking).** Spending above a budget line, receipts above the award, an open project ending within N days (your own setting, 1 to 365, default 30) and an open project past its end date.

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`projects:prepare`: start projects, add and remove budget lines, submit, withdraw, propose entries): Owner, Administrator, Manager, Auditor.
- Approve (`projects:approve`: approve or return a project, approve or reject entries, close a project, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who submitted a project or proposed an entry can never be the one who decides it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not titles, funder references, amounts, categories, descriptions or notes.

## What it does NOT do
- It moves no money and connects to no bank or funder. An approved entry is a recorded internal review, not a payment or a claim.
- No funder, donor or government rule (eligible costs, cost rates, reporting dates, procurement or audit requirements) is applied or checked. Spending can be approved that an agreement would not allow.
- Approval by a different person is a review of what was typed, not a check against receipts, contracts or the real world.
- Budgets cannot be revised after approval, and there is no re-allocation between lines; a change needs a new project. Entries cannot be edited; a correction is a new entry that a person explains.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_projects.py` (33 tests; exact figures checked against an independent fraction-based calculation) plus the static route-security, audit-coverage, tenant-isolation and boundary tests; an odd-input run (690 calls) found no crashes.
- Frontend: `frontend/tests/projects.test.js` (16 tests).
- Browser: `e2e/journey_projects.py` (Accountant, Administrator, Approver and Owner sign-ins, comparing the page with exact figures).
