# ASAVEXA Network

Businesses  <->  Accountants / Auditors / Banks / Investors / Donors / Regulators

## What it is
A way for organisations on ASAVEXA to connect with explicit, scoped, revocable consent. Information flows from a **business** (or NGO) to the other six kinds. Connections between two non-business organisations carry no data and are not offered.

## How a connection is made
1. Each organisation sets its network profile (its kind and name). Owners and administrators only (`network:manage`).
2. One side creates an **invitation** and gets a one-time code (shown once, stored only as a hash). It is sent by a separate route.
   - A business *offers* its information to an accountant, auditor, bank, investor, donor or regulator and chooses what they can see.
   - Any of those *asks* a business. The business sees exactly what is asked, can tick **fewer** boxes, never more.
3. The other side's administrator enters the code, sees what is being agreed, and accepts. Wrong codes give one generic message and, after 8 in 15 minutes, lock that person out for a while.

## What can be shared
Exactly the Financial Passport sections (identity, financial history, evidence quality, governance, reporting, audit trail), summary only by default, finished periods only by default, within a date window. The network cannot expose anything Passport sharing could not.

## Rules enforced on every open
- The connection must be active and unexpired, and the viewer must be the organisation it was made with. The business cannot open its own data through the viewer route; unrelated organisations get nothing.
- Only the business changes what a connection can see or how long it lasts. A change applies at once.
- Either side can end it at any time (reason required). Access stops immediately. Connections also end by themselves on their expiry date.
- Every connect, change, end, and open is written to **both** organisations' audit trails. The business can see which organisation opened it and when (not which person).
- The view carries a fingerprint and a disclaimer: it is what the business chose to share, not an audit opinion.

## Limits (honest)
- Verified here: service rules, API behaviour over real identity and Passport data, and a browser run with a business, an auditor, a bank and an accountant. Not verified: live PostgreSQL and the deployed site.
- A view is built live from the business's own records when opened. It is not a stored snapshot (Passport Sharing links remain the way to give someone without an ASAVEXA account a frozen copy).
- The network does not verify that an organisation is really the bank or regulator it says it is. The business decides whom to trust; the code exchange is how it knows who it is talking to.
