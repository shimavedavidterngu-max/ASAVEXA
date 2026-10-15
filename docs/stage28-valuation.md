# Stage 28: Valuation

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by a valuer or an accountant.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **valuation**: a **valuation workpaper** holding one or more **methods**, each worked out **exactly from inputs people type in**, **typed weights**, a **concluded value** and a **review by a different person**. **It reads no market data, chooses no multiples, rates or cash flows, gives no opinion of value and is not a valuation report.**

Screen: **Valuation** (menu, under Professional workspaces). API prefix `/valuation`. Stored in the shared document store (kinds `vl_case`, `vl_setting`). Reference numbers: VL-. Service methods are prefixed `vl_`.

## What it does
1. **Workpapers.** Subject, kind of subject (business, shares, property, equipment, intangible asset, other), purpose, basis of value (a label only), valuation date (not in the future) and currency (three letters).
2. **Methods** (up to 5 active per workpaper), each with a label and a weight (whole percent, 0 to 100):
   - *Multiple of a metric*: metric x multiple (up to four decimals) less optional net debt.
   - *Discounted cash flows*: 1 to 15 yearly end-of-period cash flows (none negative, at least one above zero), one discount rate in percent (up to two decimals, above 0 up to 100), an optional terminal growth in percent that must be below the rate, and optional net debt. The terminal value is the last cash flow x (1 + growth) / (rate - growth), discounted over every period. Calculated with exact decimals and rounded once to two decimals.
   - *Assets less liabilities*: total assets less total liabilities.
   A method whose result is not above zero is refused. Floating-point numbers, look-alike digits and loosely placed commas are refused.
3. **Sensitivity.** For a discounted cash flow method, the same inputs at the rate one point lower and one point higher. A rate that is not usable with the growth typed is shown as blank.
4. **Submit.** Needs at least one active method, weights adding up to exactly 100 and a rationale of at least 20 characters. The concluded value is the sum of each result x weight / 100, rounded once. The range shown is only the lowest and highest method result.
5. **Review.** A **different person approves or returns** a submitted workpaper (returning needs a reason of at least 10 characters). A returned workpaper can be edited and submitted again. An approved workpaper is final. A draft or returned one can be withdrawn with a reason.
6. **Overview.** Counts by status, totals **per currency** (approved, waiting, in progress), what needs attention (waiting for review, returned, approved valuations past the review period) and the setting (days before an approved valuation is due for review: 30 to 1095, default 365).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`valuation:prepare`: start workpapers, add and remove methods, submit, withdraw): Owner, Administrator, Manager, Auditor.
- Approve (`valuation:approve`: approve or return, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who submitted a workpaper can never be the one who approves or returns it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not subjects, labels, inputs, values or rationales.

## What it does NOT do
- It reads no market data. Every input is a person's statement; ASAVEXA cannot tell whether a multiple is comparable, a forecast reasonable or a discount rate appropriate.
- It gives no opinion of value and produces no valuation report.
- No valuation standard (IVS, IFRS 13 or any other) is applied or claimed. The basis of value is a label.
- Discounted cash flow handles end-of-period flows with one rate only. Mid-year timing, changing rates, tax and working-capital adjustments, options, and probability-weighted scenarios are not handled.
- Values in different currencies are never added together.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_valuation.py` (29 tests, exact figures checked against an independent fraction-based calculation) plus the static route-security, audit-coverage and boundary tests; an odd-input fuzz run over every write field found no crashes.
- Frontend: `frontend/tests/valuation.test.js` (15 tests).
- Browser: `e2e/journey_valuation.py` (71 checks across Accountant, Administrator, Approver and Owner sign-ins, comparing the page with exact figures).
