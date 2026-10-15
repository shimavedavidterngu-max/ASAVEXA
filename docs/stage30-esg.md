# Stage 30: ESG and carbon

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a sustainability or assurance professional.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **sustainability, ESG and carbon**: **emission records** worked out exactly from **activity data and emission factors that people type in**, **verified by a different person**, totalled by year and scope, and compared with **reduction targets approved by a different person**. **It supplies no emission factors, measures nothing, calculates no footprint of its own and applies no reporting or assurance standard. It is not an assured sustainability report.**

Screen: **ESG and carbon** (menu, under Professional workspaces). API prefix `/esg`. Stored in the shared document store (kinds `es_entry`, `es_target`, `es_setting`). Reference numbers: ER- (records), TG- (targets). Service methods are prefixed `es_`.

## What it does
1. **Emission records.** Scope (1, 2 or 3), category, description, a period within one calendar year (not in the future), a quantity (up to four decimals) and unit, an **emission factor in kg CO2e per unit** (up to six decimals) with its **source and year**. The result is quantity x factor in kg CO2e, worked out with exact decimals and rounded once to two decimals; tonnes are shown to three decimals. Floating-point numbers, look-alike digits and loosely placed commas are refused.
2. **Verification.** A record is proposed by one person and **verified or rejected by a different person** (rejection needs a reason). Nothing is edited afterwards; a wrong record is rejected and entered again. **Only verified records count.**
3. **Totals.** Verified kg and tonnes per calendar year and per scope. Amounts are all kg CO2e, so totals are added across records.
4. **Targets.** Scope (or all scopes), baseline year, baseline emissions in tonnes, reduction in percent (0 to 100) and target year. The target figure is baseline x (100 - reduction) / 100, rounded to three decimals. A **different person approves or rejects** it. For each approved target the page shows the verified tonnes for the target year and scope, the target, the exact change against the baseline and whether the figure is within the target so far.
5. **Old factors.** A verified record whose factor is more than N years older than the year of the activity is flagged (N is your own setting, 1 to 20, default 5).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`esg:prepare`: propose records and targets): Owner, Administrator, Manager, Auditor.
- Approve (`esg:approve`: verify or reject records, approve or reject targets, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who proposed a record or target can never be the one who decides it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not descriptions, quantities, factors, sources or notes.

## What it does NOT do
- It supplies no emission factors and measures nothing. A figure is only as good as the data and factor typed.
- Gases, global-warming-potential choices, market-based and location-based methods and uncertainty are not handled.
- Scope labels are a person's choice. ASAVEXA does not check scope, double counting or missing sources.
- No standard (GHG Protocol, ISO 14064, ISSB, CSRD or any other) is applied or claimed, and the target comparison is arithmetic, not a claim that a target is science-based or met in the eyes of any body.
- Verification by a different person is a review of what was typed, not a check against the real world.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_esg.py` (see the report for the count; exact figures checked against an independent fraction-based calculation) plus the static route-security, audit-coverage, tenant-isolation and boundary tests; an odd-input run over every write field (546 calls) found no crashes.
- Frontend: `frontend/tests/esg.test.js` (11 tests).
- Browser: `e2e/journey_esg.py` (Accountant, Administrator, Approver and Owner sign-ins, comparing the page with exact figures).
