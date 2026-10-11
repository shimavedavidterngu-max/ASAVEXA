# Public Finance workspace

Status: VERIFIED IN TEST ENVIRONMENT (synthetic data). Not reviewed by a public-finance or procurement professional. Not verified in staging or production.

## What it does
- **Budgets**: one currency, a period, and an amount per EXPENSE or REVENUE account. Draft, then submit; a different person approves or sends back.
- **ACTUAL**: always read from posted (non-draft) journals dated inside the budget period. EXPENSE = debits minus credits; REVENUE = credits minus debits. Nothing is typed in.
- **Available** = budget (after approved virements) minus actual minus open commitments.
- **Commitments**: money reserved for an order. Must be inside the budget period, against an approved budget's EXPENSE line, and cannot exceed what is available. Settle a commitment only after the payment is posted in the ledger, otherwise the money is counted twice.
- **Virements**: move money between EXPENSE lines. Different person approves; availability is re-checked.
- **Procurement**: quotes, an award proposal, a policy quote-count rule (written exception of 20+ characters if too few quotes), a 20+ character justification if not the lowest, approval by a different person. Approval creates the commitment.
- **Grants**: receipts (capped at the award) and spending entries that a different person approves; cannot exceed the award or fall outside the grant period.
- **Reports**: frozen snapshot with SHA-256 fingerprint, approval by a different person, CSV export only once approved (labelled confidential, spreadsheet formulas neutralised).

## Permissions
Prepare: Owner, Accountant, Finance officer. Approve: Owner, Finance officer, Approver, Manager. View: reporting read.

## Honest limits
- The default procurement policy (3 quotes, threshold 0.00) is a placeholder. Enter your own rules; they are not law.
- Single currency per budget, single period, no appropriation hierarchy or multi-year budgets.
- It reads the ledger and never writes to it.
- Tested with invented data only (backend tests, router harness, frontend tests, real-browser run).
