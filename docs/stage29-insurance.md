# Stage 29: Insurance and claims

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by an insurance professional or an accountant.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **insurance and claims**: a **register of policies**, **claims recorded against them**, **settlements or declines proposed by one person and decided by a different person**, and **money received tracked against the settled amount**. **It contacts no insurer, checks no cover or policy wording, assesses no loss, gives no insurance or legal advice, holds no money and posts nothing to the ledger.**

Screen: **Insurance and claims** (menu, under Professional workspaces). API prefix `/insurance`. Stored in the shared document store (kinds `ic_policy`, `ic_claim`, `ic_setting`). Reference numbers: IP- (policies), CL- (claims). Service methods are prefixed `ic_`.

## What it does
1. **Policies.** Insurer, policy number, type of cover (property, liability, motor, health, life, cyber, marine, crop, other), what is covered, currency (three letters), sum insured, premium, optional excess (not more than the sum insured), start and end dates (end after start, at most ten years). Two active policies cannot share an insurer and policy number. A policy can be **cancelled by an approver with a reason** if it has no claim open or waiting.
2. **Claims.** Against an active policy: date of the loss (inside the policy period, not in the future), date reported (not before the loss, not in the future), a description, the amount claimed (not more than the sum insured) and an optional insurer's claim number. A claim takes the policy's currency.
3. **Outcomes.** A person **proposes** what the insurer decided: **settled** for an amount (more than zero, not more than the amount claimed) or **declined** (no amount), with a note. A **different person approves or rejects** it (rejection needs a reason and reopens the claim). Only one proposal waits at a time; at most five proposals per claim.
4. **Money received.** Against a settled claim: amount, date received (not in the future, not before the settlement), a payment reference (unique on the claim). The total received can never exceed the settled amount; what is left is shown exactly.
5. **Overview.** "What needs attention": outcomes waiting for a decision, settled claims with money still to receive, policies ending soon, active policies past their end date. **Per currency:** active policies, sum insured, premium, open claims and the amount claimed, settled, received and still to receive. The ending-soon window (7 to 365 days, default 60) is your own setting.

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`insurance:prepare`: record policies and claims, propose outcomes, record money received): Owner, Administrator, Manager, Auditor.
- Approve (`insurance:approve`: approve or reject outcomes, cancel policies, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who proposed an outcome can never be the one who approves or rejects it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not insurers, policy numbers, descriptions, amounts, notes or references.

## What it does NOT do
- It contacts no insurer and cannot confirm an insurer's decision; that is a statement a person types in. An approved settlement is the organisation's own record, not the insurer's.
- It checks no policy wording, exclusions or cover, assesses no loss and gives no insurance, legal or claims advice.
- Premium instalments, taxes, commissions, reinsurance, subrogation and deductible application are not handled; the excess is recorded, not applied.
- Money received is a typed record. ASAVEXA sees no bank account and posts nothing to the ledger.
- Amounts in different currencies are never added together.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_insurance.py` (36 tests, with an independent fraction-based check of the money arithmetic) plus the static route-security, audit-coverage, tenant-isolation and boundary tests; an odd-input run over every write field (650 calls) found no crashes.
- Frontend: `frontend/tests/insurance.test.js` (14 tests).
- Browser: `e2e/journey_insurance.py` (73 checks across Accountant, Administrator, Approver and Owner sign-ins, comparing the page with exact figures).
