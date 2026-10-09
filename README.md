# Asavexa — Starter Codebase

**Modules built so far, in order:** Accounting Engine → Identity /
Organisation / Multi-Tenant → Evidence Vault → Reconciliation →
Financial Reporting → Period Close & Financial Controls →
**Controls & Compliance / Audit Workspace**.
Every module integrates through the previous ones' documented public
interfaces rather than around them, and none of the earlier modules'
domain or service logic has been rewritten to make a later one work.

This codebase implements the ASAVEXA Master Blueprint's Sections 7 & 8
for all seven modules: double-entry integrity, real role-based
authorization with segregation of duties, tenant isolation, a full
shared audit trail, deterministic explainable matching, provable
financial statements, an auditable period-close workflow, a control
library that proves rather than claims compliance, and clean
separation between business rules and storage technology throughout.

---

## What's actually here vs. what's a stub

**Built, tested, and passing — 277 tests, stdlib-only, zero external
dependencies required to run them:**

- **`src/asavexa/accounting/`** (14 tests) — the Accounting Engine.
  Chart of accounts, periods, draft/post/reverse journals, ledger,
  trial balance.
- **`src/asavexa/identity/`** (19 tests) — Identity / Organisation /
  Multi-Tenant. Organisations, users, memberships, sessions, a
  Role→permission matrix enforcing real segregation of duties. Stdlib
  password hashing (PBKDF2) and session tokens.
- **`src/asavexa/evidence/`** (14 tests) — the Evidence Vault. Upload,
  hash, duplicate-detect, and move evidence through a real status state
  machine. The literal `MISSING` sentinel when nothing's linked.
- **`src/asavexa/reconciliation/`** (33 + 5 = 38 tests) — Reconciliation.
  Import bank transactions with deterministic duplicate control, run
  explainable rule-based matching against the Accounting Engine's
  ledger (never AI, never a silent guess on ambiguous matches), carry
  each transaction through an explicit state machine, and finalize
  through a maker-checker review gated by the existing Identity
  permission model. See `reconciliation/README.md` for the full
  contract.
- **`src/asavexa/reporting/`** (25 + 1 = 26 tests) — Financial
  Reporting. Trial Balance, Income Statement, Balance Sheet, and
  General Ledger, all computed fresh from the Accounting Engine on
  every call — no repository layer, nothing cached or snapshotted (see
  `reporting/README.md` for why). Provenance is one named call away
  (`trace_line`), and the Balance Sheet exposes an honest imbalance
  rather than hiding it — proven to equal the period's unclosed net
  income, not a bug.
- **`src/asavexa/period_close/`** (27 + 1 = 28 tests) — Period Close &
  Financial Controls. Coordinates five named, explainable close
  controls (trial balance, unposted journals, reconciliation
  exceptions, required evidence, period integrity) sourced from
  Reporting/Accounting/Reconciliation/Evidence, then locks the period
  through the Accounting Engine's own, **unmodified** `lock_period()`
  — this module changed zero lines of `accounting/`. See
  `period_close/README.md` for the full contract, including exactly
  why post-close adjustments and retained-earnings automation were
  deliberately left unimplemented.
- **`src/asavexa/compliance/`** (40 + 12 + 1 = 53 tests) — Controls &
  Compliance / Audit Workspace. A `ControlDefinition` is not a
  `ControlExecution` is not a `Finding` is not a `Remediation` — four
  distinct entities, kept separate deliberately. Nine built-in,
  explainable controls (never a generic rules engine) call exactly one
  authoritative module each; a `FAIL` auto-opens a finding, a `WARNING`
  does not (a `finding:manage` holder decides); `finding:manage` /
  `finding:remediate` / `finding:verify` are three genuinely disjoint
  permissions, proven independent with real roles, not just declared
  so. Built, then separately **audited and hardened** — see
  `compliance/README.md`'s "Audit history" for the six real defects
  that pass found and fixed (two missing audit events, a missing
  state guard, a router/schema inconsistency, a missing production
  table, a stale docstring) before this module was considered done.
- **`src/asavexa/audit/`** — the shared audit trail every module above
  writes to (promoted out of `accounting/` when Identity needed it).
- **`src/asavexa/bootstrap.py`** — composes all six persisted modules'
  SQLite schemas into one connection, for tests and local dev
  (Reporting contributes none — see its README).
- **`tests/test_cross_module_integration.py`**,
  **`tests/test_reconciliation_integration.py`**,
  **`tests/test_reporting_integration.py`**,
  **`tests/test_period_close_integration.py`**, and
  **`tests/test_compliance_integration.py`** — the tests that
  actually matter: real users with different roles performing a maker
  step and a checker step as *different actors*, asserting the shared
  audit trail names both distinctly and that tenant isolation holds
  throughout — not just each module passing its own tests in isolation.
  The Compliance one is the broadest: control execution → WARNING →
  manual finding creation → triage → remediation → independent
  verification, with every permission boundary checked against a real
  `IdentityService`, not asserted.

Run all of it yourself:
```bash
cd asavexa
PYTHONPATH=src python3 -m unittest discover -s tests -v
# Ran 277 tests — OK
```

**Written, but NOT executed or tested** (this sandbox has no network
access to install packages — see `requirements.txt`):
- **`src/asavexa/api/`** — the FastAPI + SQLAlchemy + PostgreSQL
  production adapter for all seven modules: ORM models, repository
  implementations satisfying the exact same interfaces as the tested
  SQLite ones, Pydantic schemas, and routers (`/auth`, `/organisations`,
  `/accounts`, `/periods`, `/journals`, `/evidence`,
  `/reconciliations`, `/reconciliations/transactions`, `/reports`,
  `/period-close`, `/compliance`). Every reconciliation, reporting,
  period-close, and compliance route reuses the *same*
  `get_current_actor`, `get_current_org`, and `require_permission(...)`
  dependencies the accounting and evidence routers already used — no
  second auth mechanism was introduced, five modules running on it now.
- `schema.sql` — PostgreSQL DDL for six modules' tables (Reporting
  contributes none of its own — see `reporting/README.md`).

**Explicit stubs — nothing left with an unbuilt integration contract:**
- Alembic migrations, real MFA/OIDC, multi-currency FX conversion,
  post-close adjustments, retained-earnings automation, and a
  Financial Passport (the natural next module — see "Suggested next
  module" below) remain future work.

---

## Controls & Compliance / Audit Workspace — how it actually works

**Four distinct entities, never conflated**: a `ControlDefinition` (a
named, reusable check) is not a `ControlExecution` (one run of it,
whose `result`/`explanation` are set once and never edited — re-running
after a fix creates a *new* execution, the original `FAIL` stays on the
record) is not a `Finding` (created automatically on `FAIL`, optionally
on `WARNING`/`REQUIRES_REVIEW` — never on `PASS`/`NOT_APPLICABLE`, which
would document a problem that doesn't exist) is not a `Remediation`
(the tracked fix, requiring independent verification before its parent
finding can close).

**Nine built-in controls, zero rule engine.** Each `check_key` selects
exactly one Python method that calls exactly one authoritative module
— Accounting, Reporting, Reconciliation, Evidence, or Period Close —
and interprets its real answer. Adding a control type means adding a
method, not writing a configuration language.

**Three genuinely disjoint permissions govern findings**:
`finding:manage` (triage), `finding:remediate` (do the fix),
`finding:verify` (independently confirm it) — proven independent with
real roles and a real `IdentityService`, not just declared so in a
comment. `ACCOUNTANT` holds `finding:remediate` but not `finding:manage`
or `finding:verify`; `APPROVER` holds `finding:verify` but neither of
the others; `ADMINISTRATOR` holds `finding:manage` but neither of the
others. Every one of those nine negative/positive combinations is a
real test, not an inference from the registry.

**This module was audited and hardened as a dedicated pass**, separate
from its initial build — see `compliance/README.md`'s "Audit history."
That pass traced every request from router → permission check →
service → repository → persistence, and found six genuine defects
before declaring the module done: two state-changing operations
(`start_remediation`, `reject_remediation`) that executed correctly
but left no audit trace; a manual finding-creation path with no guard
against being called on a passing control; a router schema that
silently accepted a missing "reason" where the service required one;
a production (`schema.sql`) table set that was missing entirely for
this module; and one stale docstring reference to a file that was
never created. All six are fixed; 12 new tests (including the
module's first full cross-module integration test) prove they stay
fixed.

---

## Period Close & Financial Controls — how it actually works

**Zero changes to the Accounting Engine.** `AccountingPeriod.status`
already had `OPEN`/`LOCKED`/`CLOSED` values before this module existed
— nothing ever set `CLOSED`, but `assert_period_open_for_posting()`
already blocked posting for *any* non-`OPEN` status. This module's own
`PeriodCloseProcess.status` is a separate workflow concept (who
requested, who reviewed, who approved); the one real act of
enforcement is `approve_close()` calling the Accounting Engine's
existing, **unmodified** `lock_period()`. Two different objects' status
fields, set together by one method call — never two period systems
that could disagree.

**Five named, explainable controls**, never a bare "period cannot
close": `PERIOD_INTEGRITY`, `TRIAL_BALANCE_BALANCED` (from Reporting,
never recomputed), `UNPOSTED_JOURNALS` (from Accounting's own
`journals.list_for_org(status=DRAFT)`), `RECONCILIATION_EXCEPTIONS`
(from Reconciliation, non-blocking by default — no blueprint mandates
100% reconciliation to close, so this module doesn't invent that
requirement), and `REQUIRED_EVIDENCE` (from Evidence Vault, only for
whichever specific references the caller names as required — a
rejected or unverified one fails outright, existence alone is never
proof).

**A client can never submit `status="CLOSED"` directly.** Every
transition goes through a named method
(`request_close`/`recheck_controls`/`review_close`/`approve_close`/
`reject_close`), each checked against an explicit transition table.
`CLOSED` and `REJECTED` are both terminal; rework after rejection means
a new `PeriodCloseProcess` (`supersedes_close_process_id`), never
reopening the old one.

**Review and approval are separate, both-required steps** —
`approve_close()` raises `NotReviewedError` if no review was recorded
first. Maker-checker reuses the existing Identity permission registry
exactly: `period_close:request` (ACCOUNTANT/FINANCE_OFFICER/OWNER) is
disjoint from `period_close:review`/`period_close:approve`
(FINANCE_OFFICER/APPROVER/OWNER) — a plain ACCOUNTANT can request a
close and watch it pass every control, then is refused, by a real
`PermissionDeniedError`, the moment they try to review or approve it
themselves.

**What was deliberately left unbuilt, and documented as such rather
than improvised:** post-close adjustments (no policy for which account,
which subsequent period, or what authorization threshold is defined
anywhere) and retained-earnings automation (no convention for which
equity account should receive closed net income exists). Both would
require inventing accounting policy this codebase was explicitly told
not to invent — see `period_close/README.md`'s dedicated sections.

---

## Reconciliation — how it actually works


**Domain shape** (per its own README): `Reconciliation` (a batch — one
bank account, one statement period) and `BankTransaction` (one imported
external row, never a journal entry). A "matching decision" isn't a
separate persisted entity — it's the `match_rule` + `match_reason` +
`match_history` written onto the `BankTransaction` itself. An
"exception" isn't a separate class either — it's simply a transaction
sitting in `REVIEW_REQUIRED` or `UNMATCHED`, a first-class, visible
state.

**Matching is deterministic and provable, never AI:** a ledger
candidate qualifies only if its debit/credit exactly matches (to the
cent) and its date falls within a tolerance window (default 3 days).
Zero candidates → `UNMATCHED`. Exactly one → `MATCHED`, tagged with a
stable rule code (`EXACT_AMOUNT_AND_DATE_WITHIN_TOLERANCE` or
`MANUAL_OVERRIDE` for a human override) — never just "Matched" with no
explanation. Two or more candidates → `REVIEW_REQUIRED`, never picked
arbitrarily. A journal already claimed by one live match is excluded
from every other transaction's candidate list.

**Duplicate imports are rejected by a deterministic hash**
(`org + bank account + external ref + date + amount + description`,
unique per bank account), not a heuristic — and an import call either
succeeds completely or writes nothing, so a batch is never half-applied.

**Maker-checker reuses the existing Identity permission registry** —
five new permissions were added to `identity/domain/permissions.py`
(the same file, not a new one): `reconciliation:create`,
`reconciliation:import`, `reconciliation:match` (all held by
`ACCOUNTANT`/`FINANCE_OFFICER`/`OWNER`) and `reconciliation:approve`
(held by `FINANCE_OFFICER`/`APPROVER`/`OWNER`, not plain `ACCOUNTANT`).
A test proves the maker cannot approve their own prepared work even
though they hold every preparation permission
(`test_same_actor_cannot_prepare_and_approve_their_own_reconciliation`),
and finalizing a reconciliation requires every one of its transactions
to already be individually approved — it will not silently finalize
over an unresolved exception.

**It never touches the Accounting Engine's write path.** Only
`accounts.get()`, `journals.get()`, and `get_ledger()` are called — no
journal is ever created, posted, or reversed by this module, proven
directly by a test that snapshots the trial balance before and after a
full reconciliation and asserts it is byte-for-byte identical.

**Evidence linkage is one opaque id**, exactly like
`Journal.evidence_ref` — `Reconciliation.evidence_ref` is set by
whoever calls `attach_evidence` after uploading to the Evidence Vault
themselves. This module has no import of `EvidenceVault` at all.

---

---

## Financial Reporting — how it actually works

**No repository layer at all** — deliberately. Every other module owns
data that must persist (a posted journal, a membership, an uploaded
file, an imported bank row); a report is a *view*, not a *record*, so
`reporting/` has only `domain/` and `services/`. Every call to
`ReportingService` recomputes its answer fresh from
`AccountingEngine.get_trial_balance()`/`get_ledger()` — nothing is
cached, snapshotted, or exportable yet.

**Trial Balance, Income Statement, Balance Sheet, General Ledger** —
all four, each converting the Accounting Engine's raw debit/credit
totals into the standard normal-balance convention implied by
`AccountType`'s five values (`ASSET`/`EXPENSE` debit-normal;
`LIABILITY`/`EQUITY`/`REVENUE` credit-normal) — not a textbook formula
imposed blindly, the only convention consistent with what those five
values already mean.

**The Balance Sheet is honest about not balancing.** This starter
engine has no period-close/retained-earnings automation, so
`Assets - Liabilities - Equity` equals the period's *unclosed* net
income until someone closes it — `imbalance_amount` exposes that
directly, and a dedicated test
(`test_balance_sheet_imbalance_equals_unclosed_net_income`) proves the
imbalance is always exactly equal to net income, never an
unexplained discrepancy.

**Provenance is one named call away, not embedded by default:**
`trace_line(org_id, account_id, period_id)` returns the exact posted
ledger entries — journal id, journal number, `evidence_ref`,
`transaction_ref` — behind any one account's balance. A caller resolves
`evidence_ref` against the Evidence Vault themselves; Reporting has no
import of `EvidenceVault` at all.

**Reconciliation integration is optional and read-only:**
`ReportingService(..., reconciliation=a_reconciliation_service)` unlocks
`get_reconciliation_summary(org_id, bank_account_id)`, a plain tally of
that account's transaction statuses — proven, not just claimed, to
never change a report figure (the integration test regenerates the
Trial Balance after pulling a summary and asserts the totals are
byte-for-byte identical).

**One permission, not two:** `reporting:read`, granted to exactly the
same roles that already have `ledger:read`. There is no separate
`reporting:generate` — generating a report and reading it are the same
action here, since nothing is persisted for "generate" to create
distinctly. See `reporting/README.md` for the full reasoning.

**A real bug was found and fixed while building this module.**
`trace_line`'s round-trip through the database exposed that
`JournalRepository.update()` (SQLite and SQLAlchemy) never actually
persisted `evidence_ref`/`transaction_ref`, despite the `Journal` model
documenting them as settable after creation. This was a storage-adapter
gap — debit/credit rules, immutability, period locks, and
posting/reversal behavior were all untouched by the fix. See
`reporting/README.md`'s "Test results" section for the exact detail.

---

## How authentication and authorization work (unchanged since Identity)

1. `POST /auth/register` → `POST /auth/login` → bearer session token.
2. `POST /organisations` bootstraps the caller as `OWNER`.
3. `POST /auth/select-organisation` — a session must pick one org before
   any org-scoped call works; a role in one org confers nothing in
   another.
4. Every other endpoint requires `Authorization: Bearer <token>` and is
   checked against the session's selected `org_id` and the caller's
   role in that specific organisation.

Reconciliation's and Reporting's routers (`api/routers/reconciliation.py`,
`api/routers/reporting.py`) are the third and fourth modules to plug
into this without changing `api/deps.py`'s auth logic — it was
written once, for Accounting, and has needed no changes since.

---

## Project layout

```
asavexa/
├── README.md                    ← you are here
├── requirements.txt              ← deps for src/asavexa/api/ only
├── schema.sql                    ← PostgreSQL DDL, six persisted modules
├── .env.example
├── src/asavexa/
│   ├── audit/                     SHARED audit trail
│   ├── identity/                  IDENTITY / ORG / MULTI-TENANT (built + tested)
│   ├── accounting/                 ACCOUNTING ENGINE (built + tested)
│   ├── evidence/                   EVIDENCE VAULT (built + tested)
│   ├── reconciliation/             RECONCILIATION (built + tested)
│   │   ├── domain/                   enums, models, errors, rules, matching
│   │   ├── repository/               interfaces + SQLite implementation
│   │   ├── services/service.py       ReconciliationService — the public facade
│   │   └── README.md                 full module contract
│   ├── reporting/                  FINANCIAL REPORTING (built + tested)
│   │   ├── domain/                   enums, models, errors, rules — NO repository (see README)
│   │   ├── services/service.py       ReportingService — the public facade
│   │   └── README.md                 full module contract
│   ├── period_close/               PERIOD CLOSE & FINANCIAL CONTROLS (built + tested)
│   │   ├── domain/                   enums, models, errors, rules — no accounting rules duplicated
│   │   ├── repository/               interfaces + SQLite implementation (PeriodCloseProcess only)
│   │   ├── services/service.py       PeriodCloseService — the public facade
│   │   └── README.md                 full module contract, incl. what was deliberately left unbuilt
│   ├── compliance/                 CONTROLS & COMPLIANCE / AUDIT WORKSPACE (built, audited + tested)
│   │   ├── domain/                   enums, models (4 entities), errors, rules — no rule engine
│   │   ├── repository/               interfaces + SQLite implementation, 4 repositories
│   │   ├── services/service.py       ComplianceService — 9 built-in controls, the public facade
│   │   └── README.md                 full contract + "Audit history" (6 defects found & fixed)
│   ├── bootstrap.py                composes all six persisted modules' SQLite schemas for tests/dev
│   └── api/                        FastAPI/SQLAlchemy/Postgres adapter (untested here)
│       ├── db/                       ORM models + SQLAlchemy repositories, per module
│       ├── schemas/                  Pydantic request/response models, per module
│       ├── routers/                  auth, accounts, periods, journals, evidence, reconciliation, reporting, period_close, compliance
│       ├── deps.py                   real session auth + require_permission(...)
│       └── main.py                   FastAPI app + error handling, all modules
└── tests/
    ├── test_accounting_engine.py            14 tests
    ├── test_identity_service.py             19 tests
    ├── test_evidence_vault.py               14 tests
    ├── test_cross_module_integration.py      2 tests
    ├── test_reconciliation_service.py       33 tests
    ├── test_reconciliation_integration.py    5 tests — maker/checker + evidence + tenant isolation
    ├── test_reporting_service.py            25 tests
    ├── test_reporting_integration.py         1 test — statement generation + provenance + reconciliation context + audit
    ├── test_period_close_service.py         27 tests
    ├── test_period_close_integration.py      1 test — Accounting → Reconciliation → Evidence → Reporting → Close → maker/checker → lock → audit
    ├── test_compliance_service.py           40 tests — incl. tenant isolation, invalid transitions, audit-logging regressions
    ├── test_compliance_permissions.py       15 tests — finding:manage/remediate/verify independence, proven with real roles
    └── test_compliance_integration.py        1 test — control execution → WARNING → finding → remediation → verification, real permissions throughout
```

---

## Running it

**Core engine + tests (no dependencies needed):**
```bash
cd asavexa
PYTHONPATH=src python3 -m unittest discover -s tests -v
# Ran 277 tests — OK
```

**API layer (requires PostgreSQL + the packages in requirements.txt):**
```bash
cd asavexa
pip install -r requirements.txt
cp .env.example .env        # edit DATABASE_URL
psql < schema.sql            # or use Alembic once you add migrations
PYTHONPATH=src uvicorn asavexa.api.main:app --reload
```

---

## Known gaps (be aware before treating this as production-ready)

- **Alembic migrations exist but are unexecuted** — `migrations/` has a
  real initial migration that applies `schema.sql` (read live at
  migration-run time, not a frozen copy — see
  `docs/postgresql-runtime-verification.md`), but `alembic upgrade head`
  has never actually run against a live PostgreSQL instance in this
  sandbox (alembic itself can't be installed here).
- **No real MFA or OIDC** — unchanged since the Identity pass; because
  of this, passwords are this application's *sole* authenticator, which
  is why the Phase 4 security audit enforces NIST SP 800-63B Rev. 4's
  15-character single-factor minimum (not the 8-character MFA-paired
  floor). See `docs/security-architecture.md` for the full audit,
  including three real, concrete vulnerabilities found and fixed: a
  login-timing side-channel that leaked which emails were registered, a
  privilege-escalation path letting `ADMINISTRATOR` grant itself
  `OWNER`, and the previously-absent password length check.
- **No rate limiting on login** — evaluated and deliberately not built
  in this pass (the risk and intended production mechanism are
  documented in `docs/security-architecture.md` rather than improvised
  here); the natural fit is a reverse-proxy/gateway-level control, not
  application code.
- **Multi-currency is still intentionally limited** — unchanged since
  the Accounting pass.
- **The database-level immutability trigger in `schema.sql` is still
  commented out.**
- **Evidence file *content* storage is not yet implemented** — only
  metadata (hash, filename, size, status) is persisted;
  `docs/postgresql-runtime-verification.md` names this as a dedicated
  future phase rather than something improvised here.
- **No Row Level Security** — tenant isolation is enforced consistently
  at the repository layer (every query is `org_id`-scoped) across all
  seven modules; RLS was deliberately evaluated and not added, since
  nothing in the application currently assumes it exists as a backstop.
  See `docs/postgresql-runtime-verification.md` for the full reasoning.
- **No real HTTP/ASGI execution of the FastAPI layer** — no network
  access to install `fastapi`/`sqlalchemy`/`pydantic`/`psycopg` in this
  sandbox, confirmed by direct search of the filesystem and a live
  `pip install` attempt, not assumed. What *is* automated:
  `tests/test_api_boundary_contracts.py` (13 tests) statically and
  dynamically verifies the API layer's own logic — every router→service
  call site against real method signatures, every exception→HTTP-status
  classification against real class hierarchies, every router
  registration, every `require_permission` reference, and full SQLite/
  SQLAlchemy repository parity (16 pairs; found and fixed one real
  mismatch: `SqlAlchemySessionRepository`'s parameter naming). See
  `docs/runtime-verification.md` for exactly what that does and does not
  prove, and the exact commands to run genuine FastAPI/SQLAlchemy
  verification once those packages are installable.
- **Reconciliation's evidence-before-approval check is a caller-level
  policy, not enforced inside the module** — see
  `reconciliation/README.md`'s "Known limitations".
- **No period-scoped candidate filtering in Reconciliation's matching** —
  see the same README section.
- **Reporting has no cross-period statements** (e.g. a quarter spanning
  three monthly periods) and no export (JSON/CSV/PDF) — both were
  explicitly out of scope for this pass; see `reporting/README.md`'s
  "Known limitations".
- **Period Close has no post-close adjustment path and no
  retained-earnings automation** — both deliberately left unbuilt
  because no policy for either is defined anywhere in the blueprint;
  see `period_close/README.md`'s dedicated sections for exactly why
  inventing one would have been the wrong call.
- **Period Close's reconciliation-exceptions control is non-blocking by
  default**, and the reconciliation-to-period link it uses is a
  date-range heuristic, not a foreign key — see the same README.
- **Compliance has no bulk/scheduled control execution** —
  `ControlDefinition.frequency` is descriptive metadata only; nothing
  runs a control automatically. See `compliance/README.md`'s "Known
  limitations".
- **Session tokens don't support refresh; no login rate limiting** —
  unchanged since the Identity pass.

## Frontend

`frontend/` — vanilla JS, native ES modules, zero build step, zero npm
dependency (npm's registry is unreachable in this sandbox, the same
constraint documented throughout the backend docs). Architecture is
complete and tested (API client with full route coverage mirrored from
the real routers, auth/session state, a permission model mirroring the
backend's registry, a design system, a tiny hyperscript/router utility)
— `node --test frontend/tests/*.test.js` → **85/85 passing**. Only 2 of
9 functional areas (Dashboard, Audit Workspace) have built page UI so
far; the rest have full `ApiClient` method coverage but an honest "Not
yet built" placeholder page. See `docs/frontend-runtime-verification.md`
for the complete architecture writeup and what's built vs. pending.

## Running the full stack (Docker Compose)

`docker-compose.yml` + `Dockerfile` + `frontend/nginx.conf` (Phase 6)
define PostgreSQL + the API + the static frontend, reverse-proxied
through nginx so no CORS setup is needed for this path:
```bash
docker compose up --build
# frontend: http://localhost:8080   api: http://localhost:8000/ready
```
Not executed in this sandbox — building the images requires pulling
from Docker Hub/apt/PyPI, all blocked here (confirmed via pip, npm,
*and* a real `apt-get install postgresql`, all returning 403). Written
to be correct and runnable as-is once network access exists. CORS is
also configured (`api/main.py`, env-driven via `CORS_ALLOWED_ORIGINS`)
for anyone calling the API directly cross-origin outside this compose
setup. See `DEPLOYMENT.md` for the complete deployment guide
(environment config, migrations, backup/restore, health checks,
logging, security review, and the full readiness matrix).

## Suggested next module

**Financial Passport** is now the clear next candidate. The
`INVESTOR_REVIEWER`/`DONOR`/`REGULATOR` roles have sat with zero
general permissions since the Identity pass, specifically because
their access model was always meant to be the Passport's scoped
sharing grants, not blanket reads — that design decision has now been
load-bearing across five modules (Identity, Reconciliation, Reporting,
Period Close, and Compliance all defer to it identically). A closed
period and a clean compliance control library are both strong
"evidence quality" signals a Passport would want to expose; Reporting's
derived statements and Evidence's verification status round out the
rest of the blueprint's original Passport contents table.

Should be buildable without touching `accounting/`, `identity/`,
`evidence/`, `reconciliation/`, `reporting/`, `period_close/`, or
`compliance/` — that separation is the entire point of building it
this way.


## Advanced security & infrastructure
MFA, single sign-on, session controls, encrypted evidence, key management, tamper-evident audit chain, retention and legal holds, privacy export/erasure, residency and vendor-risk registers, security alerts, monitoring and encrypted backups. Start with `docs/security-hardening.md` (setup and runbooks) and `docs/threat-model.md` (what is and is not covered).
