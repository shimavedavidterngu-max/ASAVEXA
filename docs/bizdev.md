# Business Development workspace

Status: VERIFIED IN TEST ENVIRONMENT (synthetic data). Not reviewed by a sales or strategy professional. Not verified in staging or production.

## What it does
- **Accounts**: prospects, clients, partners with one main contact. Names are unique among active accounts. An account with open deals cannot be archived.
- **Pipeline**: opportunities move Lead, Qualified, Proposal, Negotiation. Moving backwards needs a reason. Negotiation needs a proposal that was sent. Deals past their expected close date are flagged Overdue; deals with no activity for longer than the stale limit are flagged Stale.
- **Proposals**: line items, a discount, a valid-until date, optional Evidence Vault links. A discount above the limit (default 10%) must be approved by a different person before it can be sent. Sent, accepted and declined are recorded; accepting sets the deal value to the proposal total.
- **Wins**: one person requests a win (needs an accepted proposal); a different person confirms it. Only confirmed wins count toward targets and win rate. Lost deals need a reason of 10+ characters. Closed deals are frozen.
- **Targets and forecast**: a target is an amount to win in a period, in one currency. Weighted forecast = value x stage probability (your own policy settings).
- **Reports**: frozen snapshot with SHA-256 fingerprint, approved by a different person, CSV export only once approved (confidential label, spreadsheet formulas neutralised).

## Permissions
Prepare (accounts, deals, proposals, win requests, reports): Owner, Accountant, Finance officer, Manager. Approve (discounts, wins, targets, policy, reports): Owner, Finance officer, Approver, Manager. View: reporting read.

## Honest limits
- Probabilities (10/25/50/75/90), the 10% discount limit and 30 stale days are placeholders; set your own.
- The forecast is an estimate under your policy, not a prediction.
- Currencies are never converted or added together; each is reported separately.
- It records commercial activity only. It does not post to the ledger, invoice or recognise revenue.
- One main contact per account in the screen; contact details are personal data.
- Tested with invented data only (backend tests, router harness, frontend tests, real-browser run).
