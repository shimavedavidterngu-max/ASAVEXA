# Stage 16: Treasury and Cash

Status: **VERIFIED IN TEST ENVIRONMENT** (backend tests, frontend tests and a real-browser journey). **NOT DEPLOYED** until you commit and push. Not run on the real FastAPI + PostgreSQL stack; not independently reviewed. No production-readiness, regulatory or professional-assurance claim.

## What it is
A records-and-evidence workspace for the people who look after an organisation's cash. **It never moves money and is not connected to any bank.** Everything in it is typed in by people and is only as complete and current as they keep it.

Screen: **Treasury and Cash** (menu, under Professional workspaces). API prefix `/treasury`. Stored in the shared document store (kinds `tr_account`, `tr_flow`, `tr_payment`, `tr_covenant`, `tr_setting`), so there is **no new table and no migration**.

## What it does
1. **Cash accounts and balances.** An account has a name, bank, currency and at most the last four characters of its number (a whole number is refused). A balance is recorded with its date and its source (for example the statement). It is **confirmed by a different person**. The position is the latest balance per account, shown **per currency**. Currencies are never added together or converted. Missing, out-of-date and unconfirmed balances are counted and shown.
2. **Expected cash flows.** Money in or out, with a date, amount, kind and how sure the person is (confirmed, expected, possible). Each can be changed (with a reason), marked as happened (with the real amount and date, so the difference is kept) or cancelled. A simple comparison shows how well past expectations held.
3. **Weekly liquidity forecast** (4, 8, 13 or 26 weeks). Arithmetic over the latest balances, open expected cash flows and **approved** payments. Items dated before today that are still open are counted in week 1 and said so. Anything after the last week is reported, not counted. "Possible" items are left out unless asked for. A week is flagged when cash ends below the organisation's own minimum cash (or below zero if none is set). **It is not a prediction.**
4. **Payment requests with separate approval and release.**
   - Payee, amount and account **cannot be edited** after the request. Cancel and ask again.
   - The requester cannot approve, reject or release. Only the requester can cancel.
   - At or above the organisation's limit for the currency, **two different approvers** are needed. The limit is fixed on the request when it is made.
   - The same payee and invoice reference cannot be paid twice. Warnings are shown in plain words and an approver must write a reason when any apply: first payment to this payee, same payee and amount close in date, balance below the amount, no supporting document.
   - "Released" means a named person made the payment in the bank and recorded the **bank's own reference**. A payment that settles a linked expected cash flow marks it as happened.
5. **Covenants.** A person types in the threshold from their loan agreement (must stay at or above / at or below), how often it is tested and a warning margin. Each result is judged by fixed arithmetic: met, close to the limit, or breached. A breach needs a written explanation and is **acknowledged by a different person**, who also says whether a written waiver or amendment was obtained. **Acknowledging never hides a breach.** The next test and when a result is overdue are shown.
6. **Policy settings** (approvers only): minimum cash per currency, the two-approver limit per currency, and how many days old a balance may be. Defaults are placeholders, not a standard.

## Who may do what
- View: `reporting:read` (everyone who can see the ledger).
- Prepare (accounts, balances, flows, payment requests, releases, covenants and results): `treasury:prepare` — Owner, Manager, Finance Officer, Accountant.
- Approve (confirm balances, approve or reject payments, acknowledge breaches, change policy): `treasury:approve` — Owner, Manager, Finance Officer, Approver.
- Separation is enforced by the service for every role, including the Owner: nobody decides their own work.

## What it does NOT do
- It does not connect to a bank, move money, import statements, convert currencies, or know a loan agreement's real terms or whether a waiver is valid.
- It does not post to the ledger. Reconciliation of the ledger to the bank is the existing Reconciliation module.
- It is not treasury advice, a credit facility, an audit opinion or a licensed financial service.
- The duplicate-invoice check is not guaranteed if two people send the very same request at the very same instant, and the lists have not been load-tested with large volumes.
- Dates are compared with today in UTC with one day of leeway, so a person ahead of UTC can record something dated today where they are.
- Hiding the workspace from the menu (Stage 15) is a menu change only. The server checks permissions on every action.

## Found and fixed while testing
- A very large number such as `1e30` crashed the amount check instead of being refused. It is now refused with a plain sentence (test added).
- The first design let people see Treasury only with `audit:read`, which accountants (who may prepare treasury records) do not hold, so they could not open the page. Viewing now needs `reporting:read`, and a test checks that anyone who can prepare or approve can also view.
- A bank-balance row gave no hint to someone who could not confirm it. It now says it is waiting for a different approver.
- A refused request (for example a description that is too short) used up a reference number such as CF-004 and left a gap. Numbers are now taken only after every field is accepted (test added).
- A statement dated "today" could be refused for someone ahead of UTC late at night. One day of leeway was added (test added).
- Two of my own test expectations were wrong (a forecast week that ends exactly on the minimum is not "below"; week 1 correctly adds a 3,000 rent and a 20,000 payment). The code was right.

## Verification (test environment only)
Server: `tests/test_treasury.py`. Frontend: `frontend/tests/treasury.test.js`. Browser: `e2e/journey_treasury.py` (accountant prepares, approver confirms and approves, owner releases, second approver, covenant breach and acknowledgement, another company sees and reaches nothing, server refuses what the buttons hide, menu hiding). Not tested: the real FastAPI, SQLAlchemy, Alembic, Render and Vercel stack; GitHub CI has still never run.
