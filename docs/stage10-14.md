# Stages 10 to 14: what was added after Stage 9

Status for all five: **VERIFIED IN TEST ENVIRONMENT** (unit tests, the frontend suite and a real-browser journey for each). **NOT DEPLOYED** until you commit and push. None of this has been run on the real FastAPI + PostgreSQL + Render stack, and none has had an independent review. No production-readiness claim is made.

## Stage 10: outcome measurement (Evidence Review)
- Earlier cases already recorded the baseline, the re-measured result, the residual risk text and the reopen criteria. What was missing: a **rating** (LOW, MEDIUM, HIGH), a **machine-checkable reopen threshold** and **scheduled re-checks**.
- `verify` now takes `residual_level`, `reopen_if_gaps_above` (default 0) and `recheck_after_days`. A re-check with gaps at or below the threshold stays VERIFIED and reschedules; above it, the case reopens against the rules in force at that time.
- Each case shows a measurements timeline (baseline, rejected attempts, verified, re-checks). `GET /evidence-review/cases?due_for_recheck=true` lists those due.

## Stage 11: the organisation's own expected-record rules
- The rules saying which records a figure is expected to have (ER-001 baseline plus ER-002/003) can now be replaced by the organisation: `GET/POST /evidence-review/rules`, `/rules/{version}/approve`, `/rules/{version}/reject`.
- One proposal at a time, a reason is required, the approver is not the proposer, the baseline ER-001 can never be removed or narrowed, at most 25 rules. Old versions are kept. Each case pins the version it was opened under.
- **These are the organisation's own expectations. They are not a legal or accounting standard.**

## Stage 12: one status vocabulary (Assurance)
- Six facts a record can carry (recorded, supported, reconciled, reviewed, approved, independently verified) and five flags (contested, incomplete, rejected, expired, retired). They are facts, not a score, and are not ranked.
- `GET /assurance/vocabulary`, `GET /assurance/summary` (audit:read, read-only). A test fails if any module adds a status the vocabulary does not map.
- "Independently verified" is claimed only where the system itself enforces a different person (evidence verified by someone other than the uploader, approvals by someone other than the proposer). It says how far a record was checked inside ASAVEXA, not that a figure is right.
- Not added: the stored links of Stage 13 are not in this vocabulary yet.

## Stage 13: stored Proof-to-Action links
- The existing proof graph is worked out on demand and stops at the report. Stage 13 adds **recorded links** between evidence, controls, findings, remediations, Evidence Review cases, standards, risks, risk actions and agent decisions: `/proof-links` (screen: **Proof Links**).
- A link is a **claim somebody made**, kept with its history. It can be disputed, retired and reinstated, never deleted. A different person with approval rights can confirm it (not the one who recorded it). The person who disputed a link cannot reinstate it. "An expected link is missing" can be noted (a gap) and waived by someone else.
- Evidence Review cases record their own links (case addresses finding, finding raised by control, remediation addresses finding) as SYSTEM links. If that ever fails, the case still goes ahead and the failure is audited.
- Both ends must exist in the same organisation. A link does not make the claim true and changes neither record.

## Stage 14: the nine unmeasured assistant rules now have labelled cases
- See `docs/stage5-ai-evaluation.md`. All 17 rules are measured on a small sample we built; all meet the targets there. That is not an accuracy claim about real books. A defect in the measuring harness (bank-line flags credited to the matched journal) was found and fixed.

## Still open, and not decided by this work
- An outside AI model with citations (audit item 5) is **not built**; it needs your decision.
- The CI workflows (`ci.yml`, `e2e.yml`) have never been seen to run on GitHub.
- Stage 9 shared rate limiting is still off by default (preflight, backup, `alembic upgrade head`, then `RATE_LIMIT_BACKEND=postgres`).
