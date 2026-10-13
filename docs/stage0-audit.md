# Stage 0 audit: where ASAVEXA really stands before the Proof-to-Action build

Date: 2026-10-12. Scope: read-only inspection of the repository plus a fresh test run. **No application code was changed.** The only file touched besides this report is `.gitignore` (so landing screenshots stop being re-added to your commits).

## 1. The short version
- **The strategy is not a greenfield build.** Most of its five pillars already exist in some form. The real work is connecting them, deepening them, and proving them on the live stack.
- **Strongest assets:** double-entry accounting with period controls, an Evidence Vault, a tamper-evident audit chain, findings with *separate* "resolved" and "independently verified" states enforced by segregation of duties, a Proof-to-Report graph, and a rule-based AI engine that refuses to answer without source records.
- **Biggest gaps against the strategy:** the proof graph stops at the report (it does not reach controls, risks, decisions, actions or outcomes); there is no evidence-completeness rule engine; outcome verification has no baseline or post-action measurement; the standards catalog has no official source links, effective dates or review workflow; there is no agent registry (correct, it is a later stage).
- **Biggest risks:** the real stack (FastAPI, SQLAlchemy, PostgreSQL) cannot run in the development sandbox, there is no automated CI, five tables are created at startup instead of by migration, and nothing yet proves, route by route, that every query is tenant-scoped and every write is audited.

## 2. Test baseline (actual runs)
| Check | Result | When |
|---|---|---|
| Server suite (`unittest discover`, 45 test files plus helpers) | **1233 tests, OK, 3 skipped** | 2026-10-12, this session |
| Frontend suite (`node --test`, 42 test files) | **785 of 785 pass** | 2026-10-12, this session |
| Real-browser journeys (Chromium against the real routers over HTTP): email/sign-up 31, auth 75, onboarding 66, dashboard 68 | all pass | 2026-10-11, on the same code. Not re-run today |
| Live site (seen by you in screenshots): sign-in, organisation picker, dashboard, forgot-password screen | working | earlier sessions |

What the baseline does **not** prove:
- The 3 skipped tests are the PostgreSQL backup and restore tests. They need a real PostgreSQL and its client tools, which this sandbox lacks, so **backup and restore are unverified**.
- FastAPI, SQLAlchemy and PostgreSQL are not installable here. API routers are tested through stand-ins for FastAPI, and the SQLAlchemy repositories in `api/db/` are exercised only on the live site. The live site is the only real-stack evidence.
- No email has ever been sent (no provider configured yet).
- The browser journeys use the real router functions but a SQLite-backed stand-in server, not the deployed stack.

## 3. Capability inventory
Status words: **Verified** means automated tests ran today and (where noted) you saw it live. It never means verified on PostgreSQL or under real FastAPI. **Not sufficiently verified** means implemented and unit-tested but with no real-stack or live evidence.

| Area | What exists (checked in code) | Status |
|---|---|---|
| Identity, roles, sessions, MFA, password policy, recovery | PBKDF2 hashing, 8+ char/letter/number policy, lockout, MFA, SSO config, password recovery and sign-up verification code flows, per-role permission matrix with segregation of duties | **Verified** (sign-in and recovery screen seen live). Email delivery not verified |
| Accounting engine | Double-entry, immutable posted journals, period locking, reversal | **Verified** (domain tests) |
| Reconciliation, period close, reporting | Services, routers, UI | **Verified** (tests); live use not shown |
| Evidence Vault | Evidence types and statuses (UPLOADED, VERIFIED, INCOMPLETE, DUPLICATE, CONFLICTING, EXPIRED, REJECTED), file hash, optional encryption | **Verified** (tests) |
| Tamper-evident audit | Per-organisation hash chain with platform-key MAC | **Verified** (tests). Coverage of every write is not proven (risk R7) |
| Findings and remediation | Findings OPEN, UNDER_REVIEW, REMEDIATION_REQUIRED, RESOLVED (awaiting verification), VERIFIED (a different person confirmed), CLOSED. Remediation COMPLETED vs VERIFIED. Reopen is a separate audited action | **Verified** (tests). Strategy item 4 is partly met here |
| Proof-to-Report graph | Report, line, journal, evidence; flags journals with no or unverified evidence; computed on demand, read-only | **Partially implemented** (see section 4) |
| AI assistant | Explain, Detect, Recommend, Prove. **Rule-based: no outside AI model.** Every item must carry the chain conclusion, source records, evidence, journal, treatment, framework, confidence, human-review flag, or it is refused. Detects same-person prepare/post, duplicates, backdating, outliers | **Verified** (81 tests). The strategy's "LLM with citations" layer is **Missing**; no precision/recall evaluation harness |
| Standards catalog | Frameworks and jurisdiction defaults as data, each marked "established" or "confirm", with a "not legal advice" disclaimer | **Partially implemented**: no official URLs, effective dates, version history or review workflow |
| Forensic, tax, GRC, public finance, health admin, cyber, business development, network, pilot, validation | Services, routers and pages exist (about 530 API route handlers in total) with their own audit helpers and permission checks | **Implemented but not sufficiently verified** (tests use router stand-ins; no live use shown) |
| Passport and permissioned sharing | Financial Passport, share links with sessions | **Implemented but not sufficiently verified** on the live stack |
| Agent registry, policy decisions ALLOW/DENY/REQUIRE_APPROVAL | Nothing | **Missing** (planned for Stage 7) |
| Continuous integration | No workflow files | **Missing** |

## 4. The five strategy pillars against the code
1. **Proof-to-Action Graph: partially implemented.** Today's graph is Report, Line, Journal, Evidence. Controls, findings, remediations, risks (`grc_risk`), actions (`grc_action`), forensic findings and evidence all exist as separate records, but nothing links them into one graph. Relationships are *derived on the fly*, not stored, so there is no provenance, versioning or history for a relationship, and no way to record "expected link is missing" or "these two records conflict".
2. **Independent Verification Engine: implemented for findings and remediation, not unified.** Different modules each have their own approval wording. There is no single status vocabulary (recorded, supported, reconciled, reviewed, approved, independently verified) applied across record types.
3. **Evidence-aware AI: partially implemented (rule-based).** The grounding contract is strong. There is no language model, so there are no prompt-injection or model-version concerns today. Adding one would create them.
4. **Verified Standards Registry: partially implemented.** The catalog is useful data but not yet a registry.
5. **Outcome Verification: partially implemented.** A remediation records owner, due date, completion evidence, who verified and a note. It has no baseline condition, no post-action measurement, no residual risk and no reopening criteria.

Evidence completeness and contradiction detection is also **partial**: evidence statuses and a few detectors exist, but there are no configurable "expected records" rules per record type and no per-assertion Evidence Review view.

## 5. Risk register
| ID | Risk | Evidence | Severity | Action (stage) |
|---|---|---|---|---|
| R1 | No automated CI: tests only run when someone runs them | no `.github` directory | High | Add a workflow that runs both suites on every push (Stage 1) |
| R2 | Real stack never run in the sandbox; SQLAlchemy repositories and middleware rely on the live site as their only test | `fastapi`, `sqlalchemy` not installable; 3 PostgreSQL tests skipped | High | Run the suites against real FastAPI and PostgreSQL in CI (Stage 1) |
| R3 | Schema split: 17 tables come from `schema.sql` through the single migration; 5 (`security_docs`, `passport_shares`, `organisation_profiles`, `organisation_standards`, `organisation_structures`) are created at startup, and a failure there is only logged | `schema.sql` has 17 tables; `main.py` startup hook | Medium-High | Move all tables into tracked migrations; add a startup check that fails loudly (Stage 1) |
| R4 | Tenant isolation is tested (36 tests mention cross-tenant cases) but no systematic route-by-route adversarial test proves every query and mutation is org-scoped | test search; about 530 route handlers | High for a pilot | Generate an adversarial two-tenant test over every route (Stage 1) |
| R5 | Audit coverage of writes is not proven: services use several different logging helpers and no test asserts "every write route produces an audit event" | per-service helpers; no such test | Medium | Add a coverage test (Stage 1) |
| R6 | Backup and restore unverified on PostgreSQL | 3 skipped tests | High | Run `test_backup.py` against a real database; do one restore drill (Stage 1) |
| R7 | Rate limits are in memory per server instance, reset on restart | `api/ratelimit.py` | Medium | Move to a shared store before scaling (Stage 9) |
| R8 | No email provider configured: sign-up and recovery emails have never been delivered | `GET /auth/verification/status` | Medium | Follow `docs/email-setup.md`; verify with a real mailbox |
| R9 | Standards catalog could be read as authoritative | catalog is "suggested defaults" | Medium | Registry with sources, dates and review (Stage 6) |
| R10 | AI marketing risk: the engine is rule-based and says so; it must not be described as an AI model, and no accuracy claim is supported yet | `DISCLOSURE` text in `ai/engine.py` | Medium | Evaluation harness before any claim (Stage 5) |
| R11 | End-to-end browser scripts live outside the repository, so you and any CI cannot rerun them | harness in the sandbox only | Medium | Move them into the repo with documented setup (Stage 1) |
| R12 | Email verification does not gate any feature (by design, so existing accounts are not locked out) | `docs/email-setup.md` | Low-Medium | Decide a policy before the pilot |
| R13 | Deployment hygiene: each zip overwrote `.gitignore` and re-added screenshots to commits | seen four times | Low | Fixed in this report: `.gitignore` now ignores `docs/images/landing/` |

## 6. Rollback point
- Your GitHub `main` at commit **2058ad9** is the current known-good state (it is what Render and Vercel deployed).
- Recommended: create a named restore point before Stage 1. In cmd, one line at a time:
  `git tag stage0-baseline`
  `git push origin stage0-baseline`
- To go back later: `git checkout stage0-baseline` to look at it, or ask me to prepare a revert.
- No destructive migration is proposed in Stage 1.

## 7. Proposed Stage 1 (verify before building)
Goal: remove the unknowns the later stages would build on. No new features.
1. Add CI (GitHub Actions) running the server and frontend suites on every push.
2. Run the suites on the real stack (FastAPI, SQLAlchemy, PostgreSQL) in CI; un-skip the backup tests.
3. Two-tenant adversarial test over every route.
4. Write-route audit coverage test.
5. Replace startup table creation with tracked migrations.
6. Bring the browser journeys into the repo.

Acceptance: every item above passes in CI; zero known cross-tenant defects; a documented restore drill.

## 8. Proposed first vertical slice after Stage 1 (Stages 2-4 combined, one scenario)
"A report figure looks wrong." A user opens a reported figure, sees its journals and evidence (exists today), and then sees an **Evidence Review**: what is asserted, supporting records, expected but missing records, conflicting or stale records, which links are recorded and which inferred, what is uncertain, and the action needed. They raise a finding, assign remediation, and an independent verifier confirms the result with a recorded baseline and post-action check. Built on the existing graph, Evidence Vault, findings and remediation, extended rather than replaced.

Acceptance: the scenario runs end to end through the API and browser on the real stack; a second tenant cannot see or link to any of it; every step writes an audit event; the verifier cannot be the person who did the remediation.

## 9. Decisions needed from you
1. Approve Stage 1 as the next step.
2. Confirm your production database is PostgreSQL on Render (this report assumes so; the code supports it).
3. Allow adding a GitHub Actions workflow (it adds one file under `.github/workflows`).
4. Decide whether the AI should stay rule-based for now (recommended until Stage 5) or whether you want an outside model considered, which adds cost, privacy and prompt-injection work.
