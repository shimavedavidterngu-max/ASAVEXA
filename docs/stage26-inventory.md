# Stage 26: Inventory

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack with a live browser; not reviewed by an accountant or a stock controller.

## What it is
A records-and-arithmetic workspace for the gap the Phase-1 audit listed as a missing workspace, **inventory**: a **general stock register** with **receipts**, **issues**, **weighted-average valuation**, **two-person stock adjustments** and **stock alerts**. It is separate from the clinic stock screen under Health. **It posts nothing to the ledger and follows no accounting standard or tax rule.** It keeps what people typed, does exact decimal arithmetic on the typed figures, and enforces who may decide what.

Screen: **Inventory** (menu, under Professional workspaces). API prefix `/inventory`. Stored in the shared document store (kinds `iv_item`, `iv_setting`). Reference numbers: IT-. Service methods are prefixed `iv_`.

## What it does
1. **Items.** Item code (unique among active items, upper-cased), name, unit, currency (three letters), reorder level (whole number, default 0) and location. An item with no stock on hand and nothing waiting can be **discontinued** by an approver, with a reason. A discontinued item takes no more movements, and its code can be used again.
2. **Receipts.** Quantity (whole number, more than zero), unit cost (text such as 150.00, at most two decimals, more than zero), date (not in the future) and a reference such as a delivery note number. Applied at once. Floating-point numbers are refused.
3. **Issues.** Quantity, date and reference. Applied at once. **Stock can never go below zero**: an issue larger than the quantity on hand is refused.
4. **Valuation.** Weighted average cost: value on hand divided by quantity on hand. An issue or a downward adjustment removes quantity x average cost, rounded to two decimals; taking out the last unit removes exactly what is left, so no rounding residue stays behind. Everything is exact decimal arithmetic on the typed figures.
5. **Adjustments.** A person proposes an increase or a decrease with a kind of reason (count difference, damage, loss, other) and a written reason of at least 10 characters. An increase uses the average cost, or a unit cost that is typed (required when no stock is on hand). A **different person approves or rejects** (rejection needs a reason). The decrease is checked again at approval, so stock still cannot go below zero. At most five adjustments wait at once on one item.
6. **Overview.** "What needs attention": out of stock (items with a reorder level), at or below reorder level, adjustments waiting, items with stock not moving within your window (default 180 days, 30 to 730). Quantity and value for active items **per currency**, counts, the setting and the limits.

## Who may do what
- View (`audit:read`): everyone who holds it.
- Prepare (`inventory:prepare`: add items, record receipts and issues, propose adjustments): Owner, Administrator, Manager, Auditor.
- Approve (`inventory:approve`: approve or reject adjustments, discontinue items, change the setting): Owner, Approver, Manager.
- Anyone who can prepare or approve can also view. The person who proposed an adjustment can never be the one who approves or rejects it, enforced by the service for every role including the Owner. The audit trail records reference numbers and outcomes, not the typed text, references or amounts.

## What it does NOT do
- It posts no journal entry, does not value stock at net realisable value, and does not check the figures against invoices or delivery notes.
- The value is arithmetic on typed figures, not an accounting or tax result. Only weighted average cost is supported. FIFO, batches, serial tracking, units of measure conversion, multiple warehouses and stock transfers are not handled.
- A receipt, an issue or an adjustment is a person's statement. ASAVEXA cannot tell whether the stock is really on the shelf.
- Amounts in different currencies are never added together.
- Two people sending the same request at the same instant are not guaranteed to be caught by the state checks, and nothing has been load-tested. Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Verification (test environment only)
- Server: `tests/test_inventory.py` (32 tests) plus the static route-security, audit-coverage and boundary tests.
- Frontend: `frontend/tests/inventory.test.js` (13 tests).
- Browser: `e2e/journey_inventory.py` (61 checks across Accountant, Administrator, Owner and Approver sign-ins, comparing the page with the exact arithmetic).
