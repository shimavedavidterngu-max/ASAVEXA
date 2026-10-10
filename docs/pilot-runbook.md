# Real Pilot runbook: accounting firm and four small businesses

Purpose: find out, with real work, whether ASAVEXA is workable for a firm and its small-business clients. A pilot of this size can show "workable for these organisations". It cannot prove it works for everyone.

## Shape
VERA (the firm) runs the pilot. Up to 12 client organisations can join (start with 4). The Evidence / Trust layer is ASAVEXA itself: evidence vault, ledger, reconciliation, audit trail and Financial Passport.

## Before you start
1. Each SME has its own ASAVEXA organisation. The SME owner signs a short written consent letter (what is shared, that they can leave any time, that leaving removes their data from results).
2. The SME owner makes your firm manager an **Administrator** of the SME organisation, and adds firm staff as Accountants. Without access, the platform cannot measure that client for that person; it is listed as "left out", never guessed.
3. Firm staff are also members of the firm organisation (so adoption can be counted).
4. In Real Pilot: Create pilot, add each client (choose it, give its consent reference, optionally its "before ASAVEXA" minutes for audit preparation and reports), set targets, then Start the pilot.

## The eleven measures
| Measure | Source | How |
|---|---|---|
| Onboarding time | Measured | Days from kickoff until accounts, a posted journal, evidence and a bank import all exist |
| Transaction processing | Measured | Median hours from draft to posted |
| Evidence completeness | Measured | % of posted journals with verified evidence (same definition as the Passport) |
| Reconciliation rate | Measured | % of bank transactions reconciled |
| Exception rate | Measured | Exceptions per 100 items handled |
| Report generation | Measured | % of report runs that succeeded; every client must have produced one |
| Audit preparation time | Reported | % time saved against the stated baseline |
| User errors | Measured | Corrections (reversals, deleted drafts, rejections) per 100 work actions |
| User satisfaction | Reported | Survey, 1 to 5 |
| Accountant adoption | Measured | % of firm accountants active in 30 days |
| Passport usefulness | Reported | Survey rating and logged uses |

A measure with too few records shows "Not enough data yet" and no headline figure. Group survey averages are hidden below 3 people.

## Weekly rhythm
- Firm staff record time for audit preparation, reports and month-end; anyone reports problems and mistakes (honest entries matter most).
- Each person answers the survey every few weeks (same round name replaces an earlier answer).
- Manager resolves issues, recalculates results, takes a snapshot (fingerprinted, aggregate only).

## Finishing
Take a final snapshot, build the report (download), then mark Completed (final). Suggested exit questions: did every client become operational within target? did evidence and reconciliation reach target on real data? would the accountants keep using it unprompted?

## Privacy and limits
- A client sees only its own entries; never other clients, targets or results.
- A client can leave at any time; its data is excluded from every result.
- Results include only clients the viewer can read themselves.
- Verified here: logic, API rules, browser flow on synthetic data. Not verified here: live PostgreSQL, the deployed site, and any real organisation's data.
