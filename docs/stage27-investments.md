# Stage 27: Investments

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by an investment professional or an accountant.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **investments**: a **register of holdings**, **typed purchases**, **sales approved by a different person**, **weighted-average cost**, **typed dated prices** and **gain or loss arithmetic**. **It reads no market data, gives no investment advice, holds or moves no money, posts nothing to the ledger and follows no accounting standard or tax rule.** It keeps what people typed, does exact decimal arithmetic on the typed figures, and enforces who may decide what.

Screen: **Investments** (menu, under Professional workspaces). API prefix `/investments`. Stored in the shared document store (kinds `im_holding`, `im_setting`). Reference numbers: HD-. Service methods are prefixed `im_`.

## What it does
1. **Holdings.** Name, optional identifier (unique among active holdings, upper-cased), asset class (equity, bond, fund, deposit, property, other), currency (three letters) and the account or custodian. A holding with no units left and no sale waiting can be **closed** by an approver, with a reason. A closed holding takes no more trades, prices or sales, and its identifier can be used again.
2. **Purchases.** Units (up to four decimals, more than zero), price per unit (up to four decimals, more than zero), an optional fee (up to two decimals), a date (not in the future) and a contract note or reference. Cost = units x price rounded to two decimals, plus the fee. Applied at once. Floating-point numbers, look-alike digits and loosely placed commas are refused.
3. **Weighted-average cost.** The cost of all units held divided by the units held. A sale removes the cost of the units sold at that average, rounded to two decimals; selling every unit removes exactly what is left, so no rounding residue stays behind.
4. **Sales.** A person proposes a sale (units no more than held, fee no more than units x price). A **different person approves or rejects** it (rejection needs a reason). On approval the units are checked again, the proceeds (units x price less the fee), the cost removed and the **gain or loss already realised** are worked out and kept. At most five sales wait at once on one holding.
5. **Prices.** A person types a price per unit, the date it applies to (not in the future) and its source. The newest **date** is the current price, not the last one typed. Market value = units x that price; gain or loss so far = market value less cost. A price older than your window (default 30 days, 7 to 365) is flagged. Nothing is fetched.
6. **Overview.** "What needs attention": sales waiting, holdings with units but no price, holdings with an old price. **Per currency:** active holdings, cost, how many holdings have a price, their market value and unrealised gain or loss (holdings without a price are left out of those two figures and counted separately), and the gain or loss already realised (closed holdings included).

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`investments:prepare`: add holdings, record purchases and prices, propose sales): Owner, Administrator, Manager, Auditor.
- Approve (`investments:approve`: approve or reject sales, close holdings, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who proposed a sale can never be the one who approves or rejects it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not names, accounts, references, prices or amounts.

## What it does NOT do
- It reads no market data and fetches no prices. A price is a typed statement; ASAVEXA cannot check it.
- It gives no investment advice, ranks nothing and predicts nothing.
- It posts no journal entry and applies no accounting, tax or performance standard. Gain or loss is arithmetic on typed figures, not a fair-value, impairment or tax result.
- Only weighted-average cost is supported. Tax lots, FIFO, accrued interest, dividends, splits, fees other than the one typed per trade, and currency conversion are not handled.
- It cannot know about holdings or trades nobody records, and cannot tell whether the holding exists.
- Amounts in different currencies are never added together.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_investments.py` (30 tests) plus the static route-security, audit-coverage and boundary tests.
- Frontend: `frontend/tests/investments.test.js` (12 tests).
- Browser: `e2e/journey_investments.py` (67 checks across Accountant, Administrator, Approver and Owner sign-ins, comparing the page with the exact arithmetic).
