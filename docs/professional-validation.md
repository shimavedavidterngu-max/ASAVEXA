# Professional Validation

Software testing is not accounting validation. ASAVEXA's own tests prove the software follows its rules; they cannot prove that a treatment
is right under IFRS or that a control is adequate. That needs professional judgement from named people.

This module **records** that judgement. It never produces it.

## What reviewers look at (in this order)

1. **Accounting treatment**  2. **Controls**  3. **Evidence**  4. **Reporting**  5. **Audit workflow**  6. **Security**  7. **Professional judgement**

Each stage has a plain question and a non-exhaustive list of prompts (Professional Validation → *How it works*). The prompts are aids, not a
standard; the reviewer's own methodology governs.

## Who can be on the panel

ICAN / ACCA / CPA / CA / CIMA members, audit partners, IFRS and IPSAS specialists, tax professionals, internal auditors, cybersecurity
professionals, accounting academics, software architects, data scientists and regulators or sector specialists. Each reviewer declares the
**specialisms** they are competent in; a reviewer can only be assigned to a stage their specialisms cover.

**Credentials are declared, not checked.** A credential shows as *Declared* until an owner or administrator records *how* they verified it
(for example "looked up on the ICAN public register, 1 Oct 2026"). ASAVEXA checks nothing itself. A reviewer cannot verify their own credential.

## How an engagement runs

| Step | Who | Rule enforced by the server |
|---|---|---|
| Create | owner / administrator | Freezes a snapshot of counts and statuses (no names or amounts) and its SHA-256 |
| Assign | owner / administrator | Reviewer must be active and competent for the stage |
| Open | owner / administrator | Reviews can only be recorded while open |
| Declare independence | the reviewer (or an owner on behalf, with a source reference) | Four confirmations must all be true; otherwise the reviewer cannot review or sign |
| Review + sign | the reviewer (or an owner on behalf, with a source reference) | Needs scope, basis, a conclusion and a competence confirmation; comments/disagreement need observations; a disagreement needs a major or critical one; "unable to assess" needs the limitation |
| Respond | owner / administrator | Every major or critical observation needs a management response before completion |
| Complete | owner / administrator | Every stage needs enough signed reviews with a conclusion |

* A reviewer linked to an ASAVEXA account acts **only as themselves**. Not even an owner can sign for them.
* An unlinked reviewer's documents are recorded by an owner **with a reference to the signed document**; the record says it was done on their behalf.
* A signed review is immutable. A changed mind is a new version; the old one stays on record as *superseded*.
* If a reviewer is later deactivated or declares a conflict, their review stops counting.

## Outcomes (computed only from signed reviews)

* **Incomplete**: some stage lacks enough signed reviews, or a reviewer was unable to assess.
* **Validated**: every stage covered, all reviewers concur.
* **Validated with reservations**: covered, but there are comments or major/critical observations.
* **Not validated**: at least one reviewer disagrees.

## The statement

Completing an engagement issues a statement: outcome, who concluded what (with credential state *at signing*), the frozen snapshot, limitations
and the disclaimer. It carries a SHA-256 fingerprint and, when encryption keys are configured, a keyed signature. *Check the statement again*
recomputes both. If the live data has changed since the snapshot, the page and the statement check say so.

The fingerprint proves the statement was not edited. It does **not** say the reviewers are right.

## What this is not

Not an audit opinion, an assurance report or a certification by ASAVEXA. Reviewers act on their own professional responsibility. ASAVEXA cannot
judge a conclusion, verify a person's identity, or know whether the reviewer's firm has the right to practise in a jurisdiction.

## Setting it up

1. Owner or administrator: **Professional Validation → Reviewer panel → Add a reviewer**. Link them to an ASAVEXA account if they have one
   (give them a Reviewer, Auditor or External Auditor role: they need `audit:read`).
2. Record how each credential was verified.
3. **Engagements → New validation engagement**, choose stages and reviewers needed per stage, open it, assign reviewers.
4. Reviewers declare independence and sign. Management responds to serious observations. Complete.

## Audit trail

Every action is written to the audit trail (and its tamper-evident chain when keys are configured): `VALIDATION_REVIEWER_ADDED`,
`…CREDENTIAL_VERIFIED/REJECTED`, `…ENGAGEMENT_CREATED/OPENED/COMPLETED/WITHDRAWN`, `…REVIEWER_ASSIGNED`, `…INDEPENDENCE_DECLARED`,
`…REVIEW_SIGNED`, `…OBSERVATION_RESPONDED`, `…SNAPSHOT_REFRESHED`.
