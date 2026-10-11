# Financial Analysis workspace

Menu: **Professional Workspaces** (list and honest status of each workspace) and **Financial Analysis**. Viewing needs `reporting:read`; preparing needs `analysis:prepare`; approving needs `analysis:approve`.

## Tabs
- **Overview**: totals for the chosen period, data-quality warnings, and the definitions used.
- **Ratios**: liquidity, profitability, leverage and efficiency ratios. Each shows its formula and the accounts behind it ("Show working"). A ratio whose accounts are not classified says **Needs setup**; one with a zero denominator says **Not meaningful**. Nothing is guessed.
- **Variance**: this period against the previous one. Lines above your percent and amount thresholds are flagged; people can add a reason note (name and time recorded).
- **Budget**: a *manually entered comparison budget* per period (versioned). It is not an approved budget; the Public Finance slice will supersede it.
- **Forecast**: scenarios (months, revenue/expense growth, opening cash) with a month-by-month projection, a sensitivity table, and a break-even calculator. Always labelled FORECAST and never written to the ledger.
- **Reports**: freeze the figures into a report, submit for review, a *different* person approves or sends back (with a reason), "Check it is intact" re-verifies the fingerprint and compares against the ledger now, approved reports download as CSV.
- **Setup**: classify accounts (cash, receivables, inventory, payables, ...) and set variance thresholds.

## Definitions
Balance-sheet accounts use the balance at the end of the period. Revenue and expenses use the movement inside the period. Total equity = assets − liabilities (so it includes profit not yet closed). Drafts are excluded; reversed journals stay in. Amounts use exact decimal arithmetic, rounded half-up to 2 places.

## Limits
Single currency only. Ratios are indicators for professional judgement, not advice. Tested with synthetic data only; not reviewed by an accountant.
