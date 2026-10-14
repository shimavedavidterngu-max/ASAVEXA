# Stage 17: Procurement

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack; not independently reviewed. No production-readiness, regulatory or professional-assurance claim.

## What it is
A records-and-checks workspace for the chain **supplier → contract → purchase order → delivery → invoice (three-way match) → payment record → supplier review**. **It does not buy anything, make any payment, read a contract or confirm that goods really arrived.** Everything in it is typed in by people and is only as complete and honest as they keep it.

Screen: **Procurement** (menu, under Professional workspaces). API prefix `/procurement`. Stored in the shared document store (kinds `pc_supplier`, `pc_contract`, `pc_order`, `pc_delivery`, `pc_invoice`, `pc_review`, `pc_setting`), so there is **no new table and no migration**.

## What it does
1. **Suppliers.** Registered with a kind, country, contact and an honest yes/no answer to "is anyone here connected to this supplier?" (a "yes" needs a description of at least 10 characters). A **different person approves** the supplier, and must write a reason when the supplier is a connected party. An approved supplier can be suspended (with a reason) and reinstated by someone other than the person who suspended it. Duplicate names (ignoring capitals) are refused. Nothing can be ordered from, or contracted with, a supplier that is not approved.
2. **Contracts.** Typed in from the signed agreement: title, currency, a ceiling and start and end dates. A different person approves it. The page shows how much is committed against the ceiling, how much remains, and warns a set number of days before the end. A contract can be terminated with a reason.
3. **Purchase orders.** Lines of description, quantity (up to 3 decimals) and unit price. **The total is worked out by the server** with exact decimals, each line rounded half-up to 2 places. An order may name a contract, which must be approved, for the same supplier and currency, and in force. A different person approves it. At or above the organisation's limit for the currency **two different approvers** are needed, and nobody can give both approvals. The contract and supplier are checked again when the approval is given, and **an approval that would take the contract over its ceiling is refused**. Only the person who raised an order can cancel it, and only before goods or an invoice exist. An approved order can be closed with a reason, but not while an invoice is waiting for a decision.
4. **Deliveries.** Recorded against an approved order for the quantities that arrived. **The person who raised the order cannot record its delivery.** More than is still outstanding is refused. A delivery date in the future is refused. The order shows received, invoiced and outstanding for every line, and whether it is past its expected date.
5. **Invoices and the three-way match.** An invoice is compared with the order and with the receipts. It is an **exception** (never silently accepted) when:
   - the invoice is in a different currency from the order (such an invoice can never be approved, only rejected);
   - the quantity invoiced so far is more than has been recorded as received (counted across all live invoices, so two small invoices cannot add up to more than was received; a rejected invoice frees its quantity);
   - a unit price is above the order price by more than the tolerance (default 2%; a cheaper price is fine).
   A clean match still needs a different person to approve it. An exception needs a different person **and a written reason of at least 10 characters**, which is kept on the invoice. The same supplier's invoice number is never accepted twice (capitals ignored), unless the earlier one was rejected.
6. **Recording payment.** "Paid" is a record, not a payment. Either link a **Treasury payment** (it must be released, in the same currency, for the exact invoice total, to a payee with the supplier's name, and not already used for another invoice) or enter a date and the bank's own reference.
7. **Supplier reviews.** One per supplier per period. Scores of 1 to 5 for delivery, quality, price and service; the average is plain arithmetic to one decimal place, not a rating issued by ASAVEXA. A score of 1 or 2 needs a comment. A supplier with deliveries and no review is listed as needing one.
8. **Policy settings** (approvers only): the price tolerance (0 to 20%), the two-approver limit per currency, and how many days before a contract ends to warn. Defaults are placeholders, not a standard or a legal requirement.
9. **Overview.** A "what needs attention" list: suppliers, contracts and orders waiting for approval, contracts ending soon or already ended, contracts nearly at their ceiling, late deliveries, invoice exceptions, invoices waiting for a decision, approved invoices not yet paid and suppliers needing a review.

## Who may do what
- View: `reporting:read` (everyone who can see the ledger).
- Prepare (register suppliers, draft contracts, raise, cancel and close orders, record deliveries and invoices, record payment, review suppliers): `procure:prepare` — Owner, Manager, Finance Officer, Accountant.
- Approve (approve suppliers, contracts, orders and invoices; reject orders and invoices; suspend, reinstate and terminate; change policy): `procure:approve` — Owner, Manager, Finance Officer, Approver.
- Separation is enforced by the service for every role, including the Owner: nobody decides what they created.

## What it does NOT do
- It does not buy, pay, e-sign, connect to a supplier or a bank, read a contract, check a supplier's identity or tax status, or verify that goods or services were really received.
- A match compares typed-in records. It is **not an audit opinion**, not procurement-law advice and does not show compliance with any procurement rule.
- It does not post to the ledger.
- Two people sending the very same request at the very same instant are not guaranteed to be caught by the duplicate checks, and lists have not been load-tested with large volumes.
- Dates are compared with today in UTC with one day of leeway.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Found and fixed while testing
Honest account: **the tests found no defect in the server rules.** What was caught, and by what:
- While wiring the page (before any test ran): the Deliveries and invoices tab built its order pickers from the Orders tab list, which follows that tab's filter, so choosing "Closed" there would have emptied the pickers. It now loads approved orders separately (covered by the journey and page tests).
- While wiring the page: the invoice form's "received and not yet invoiced" starting quantities were first worked out with ordinary floating-point subtraction. They are now worked out in whole thousandths so 0.3 − 0.1 is exactly 0.2 (test added).
- Every failure in the first test runs was a mistake in my own tests, not in the product: helper dates later than the test clock (the service correctly refused a delivery or invoice dated in the future); a helper that replaced an empty list with default lines; a wrong expectation about how many units a rejected invoice frees; two wording checks in the browser journey (a capital letter; a "waiting for a different approver" message that a role who cannot approve correctly never sees). Each was corrected in the test, and the service was left unchanged.

## Verification (test environment only)
Server: `tests/test_procurement.py` (50 tests: policy, supplier approval and connected parties, contract rules and ceilings, order approval and dual approval, delivery limits and receiver separation, the three-way match flags and tolerance boundary, duplicate invoice numbers, the override note, the currency block, Treasury-payment link rules, manual payment, reviews, isolation between organisations, audit coverage, reference numbers not used up by refused requests, router guards read from the source, roles). The full server suite also runs the existing route-security, audit-coverage and API-boundary checks over the new router. Frontend: `frontend/tests/procurement.test.js` (30 tests). Browser: `e2e/journey_procurement.py` (accountant registers, approver approves, a connected supplier needs a reason, contract, order, a ceiling breach refused, delivery refused for the requester and accepted for another person, over-delivery refused, partial delivery, an exception invoice, a duplicate invoice number refused, override with a written reason, payment linked to a released Treasury payment, payment by hand, a low-score review, policy, the server refusing what the buttons hide, another company seeing and reaching nothing, audit entries). Not tested: the real FastAPI, SQLAlchemy, Alembic, Render and Vercel stack; GitHub CI has still never run.
