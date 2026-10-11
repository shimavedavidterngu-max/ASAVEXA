# Governance, Risk and Compliance workspace

Menu: **Governance, Risk and Compliance** (also in Professional Workspaces). Four tabs: Overview, Risks, Actions, Obligations. **Download register (CSV)** exports all three registers, labelled confidential.

## Who can do what
| Permission | Held by | Lets you |
|---|---|---|
| `audit:read` | Owner, Administrator, Finance officer, Approver, Manager, Auditor, Reviewer, External auditor, Read-only | see the registers and dashboard |
| `grc:prepare` | Owner, Administrator, Finance officer, Manager | add and edit risks, actions and obligations; start treatment; request acceptance; mark actions done; mark obligations met; close or reopen risks |
| `grc:approve` | Owner, Approver, Manager | approve or send back a risk acceptance; verify or send back a completed action; set the risk appetite |

The server (not only the screen) refuses a person deciding an acceptance they asked for, and verifying an action they completed.

## Risks
Each risk has a title, category, owner, a **before-controls (inherent)** and **after-controls (residual)** score, a chosen treatment (reduce, share, stop, accept) and a next review date.
- Score = likelihood (1 to 5) x impact (1 to 5). Bands: 1-4 Low, 5-9 Medium, 10-16 High, 17-25 Critical. These are fixed; ASAVEXA does not estimate probabilities or money.
- A residual score lower than the inherent score needs a written reason. Residual cannot exceed inherent.
- You can link existing **Controls** (from Controls & Compliance). Linking does not prove the control works; run it there.
- **Risk appetite** is a single number set by an approver (default 9): a residual score above it is "above appetite".
- Status path: Assessed -> Being treated -> (Accepted | Closed). Accepting a risk **within appetite** takes effect at once and is recorded. Accepting one **above appetite** waits for a different person to approve. Every acceptance needs a reason and a future review-by date; an accepted risk can be reopened.
- A risk cannot be closed while it has open or unverified actions, or a pending acceptance.

## Actions
Owner, due date, status Open -> Done -> Verified (or Cancelled). Marking done needs a description and may attach Evidence Vault files. A **different** person verifies or sends it back with a reason.

## Obligations
A register of what you must do and when. You enter every obligation yourself, with the authority it is owed to, where in the source (section, clause), an optional link, owner, frequency and next due date. **ASAVEXA ships no legal text and does not check what you enter.**
- State: On track, Due soon (within 30 days), Overdue, Met (one-off), Retired.
- **Mark met** records your statement, the date, a note and optional evidence, then moves the next due date forward by the frequency from the previous due date (so a late filing does not shift the calendar). If several periods were missed it moves one period at a time, so the register stays honestly overdue until each is recorded.

## Overview
5 by 5 residual heat map of live risks, counts, and lists of what needs attention: above appetite with no action plan, acceptances waiting, reviews overdue, actions overdue or waiting for verification, obligations overdue or due soon.

## Limits
- Tested with synthetic data in the build environment. Not reviewed by a risk or compliance professional.
- Scores are judgements. "Met" is an attestation. Neither is checked by ASAVEXA.
- No legal content, no automatic control testing schedule, no policy library or board pack yet.
- Not legal advice, not an audit opinion, not an assurance report.
