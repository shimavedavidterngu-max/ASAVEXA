# Period Close & Financial Controls

**"Don't just close the period. Prove that it was properly closed."**

A **control/workflow layer** that coordinates existing modules to
decide, explainably and auditably, whether an accounting period may be
locked — and then locks it using the Accounting Engine's own,
unmodified mechanism.

## Architecture — why there is no second period system

`AccountingEngine`'s `PeriodStatus` enum has always had three values —
`OPEN`, `LOCKED`, `CLOSED` — but until now nothing ever set `CLOSED`,
and `assert_period_open_for_posting()` already blocks posting for
*any* non-`OPEN` status, `LOCKED` and `CLOSED` alike. That meant this
module could be built with **zero changes to the Accounting Engine**:

- This module's own `PeriodCloseProcess.status` (`REQUESTED` →
  `READY_FOR_CLOSE`/`CONTROLS_FAILED` → `CLOSED`/`REJECTED`) is a
  **workflow** concept — who requested, who reviewed, who approved,
  which controls passed — persisted here because it must survive
  across separate maker and checker calls.
- The **actual enforcement** — "can anyone still post into this
  period" — is never reimplemented. `approve_close()` calls
  `AccountingEngine.lock_period()` **unchanged**, which sets the
  authoritative `AccountingPeriod.status` to `LOCKED`. There is exactly
  one place in the whole codebase that can make posting fail:
  `accounting/domain/rules.py::assert_period_open_for_posting`, and
  this module never touches it.

So "this workflow reached `CLOSED`" and "the accounting period is
`LOCKED`" are two different objects' status fields, set together by
one method call — not two period systems that could ever disagree.

## Close lifecycle

**`approve_close` re-verifies readiness immediately before locking** —
found during the cross-module integrity audit performed after this
module was first built: `approve_close` originally trusted the
`READY_FOR_CLOSE` status set by an earlier `request_close`/
`recheck_controls` call without re-checking. In the window between
that check and a checker's approval, accounting state can legitimately
change (a new draft journal appears, reconciliation regresses). Trusting
the stale snapshot would have let a period lock over a control that no
longer actually passed. `approve_close` now re-runs
`check_close_readiness` immediately before transitioning to `CLOSED`;
if anything has regressed, the process moves to `CONTROLS_FAILED`
instead (never straight to `CLOSED`, never silently) and the call
raises. Proven by
`test_approve_close_re_verifies_readiness_and_catches_a_regression`.

```
REQUESTED → READY_FOR_CLOSE ⇄ CONTROLS_FAILED
                  ↓
          CLOSED | REJECTED   (both terminal)
```

`request_close()` immediately evaluates every control and lands
directly in `READY_FOR_CLOSE` or `CONTROLS_FAILED` — there is no
externally-observable bare `REQUESTED` state to poll. `recheck_controls()`
lets a maker re-run the evaluation after remediating a failure (e.g.
posting a flagged draft) without creating a new process. `review_close()`
and `approve_close()` are separate, both-required steps —
`approve_close()` raises `NotReviewedError` if no review has been
recorded yet. Rework after `REJECTED` means a **new** `PeriodCloseProcess`
(`supersedes_close_process_id`), never reopening the old one — the same
"never silently reopen a terminal record" discipline Reconciliation
established.

A client can never submit `status="CLOSED"` directly — every
transition happens through a named service method
(`request_close`/`recheck_controls`/`review_close`/`approve_close`/
`reject_close`), each of which calls
`domain/rules.py::assert_transition_allowed` before writing anything.

## Close controls

Five named, independently identifiable controls, each returning a
`ControlFinding` (`control`, `status`, `blocking`, `message`,
`reference`) — never a bare "period cannot close":

| Control | Blocking? | Source | Notes |
|---|---|---|---|
| `PERIOD_INTEGRITY` | Yes | this module | the period resolves for this exact `org_id` — also how a foreign/invalid org is caught |
| `TRIAL_BALANCE_BALANCED` | Yes | **Reporting** (`get_trial_balance`) | never recomputed here; if Reporting says unbalanced, this control fails with the real figures, never forced to pass |
| `UNPOSTED_JOURNALS` | Yes | **Accounting** (`journals.list_for_org(status=DRAFT)`) | any draft left in the period blocks close |
| `RECONCILIATION_EXCEPTIONS` | **No** (`WARNING`) | **Reconciliation** (`list_reconciliations`/`list_transactions`) | see below for why non-blocking is the default |
| `REQUIRED_EVIDENCE` | Yes, but only if evidence was actually required | **Evidence Vault** (`get_evidence`) | `NOT_APPLICABLE` if the caller named none; a rejected or unverified reference fails outright — existence alone is never proof |

**Why `RECONCILIATION_EXCEPTIONS` doesn't block by default:** no prior
module or blueprint document defines "100% reconciled" as a hard
precondition for closing a period, and inventing one here would be
exactly the kind of unstated policy the build brief says not to
invent. Outstanding items are still fully surfaced (transaction ids,
counts) — visible, never hidden — just not blocking until an
organisation-level policy says it should be. The `blocking` field is
on every `ControlFinding`; making this control blocking later is a
one-line change, not a redesign.

**Reconciliation-to-period linkage is a date-range heuristic, stated
explicitly:** `Reconciliation` batches carry `period_start`/`period_end`
dates with no foreign key to `AccountingPeriod` (see
`reconciliation/README.md`) — this control considers a reconciliation
"relevant" when its date range overlaps the accounting period's
`start_date`/`end_date`. This is a heuristic, not a guarantee, and is
documented here rather than silently assumed.

**`REQUIRED_EVIDENCE` requires no universal policy either** — this
module does not assert "every close needs an uploaded document."
Callers pass `required_evidence_refs: List[str]` naming whichever
specific evidence *they* consider mandatory for *this* close; with none
supplied, the control is `NOT_APPLICABLE`, not `FAILED`.

## Permissions

Four new permissions, added to the existing registry
(`identity/domain/permissions.py`), following its exact
maker/checker precedent from Reconciliation:

| Permission | Roles | Mirrors |
|---|---|---|
| `period_close:request` | OWNER, ACCOUNTANT, FINANCE_OFFICER | `reconciliation:import`/`create`/`match` |
| `period_close:review` | OWNER, FINANCE_OFFICER, APPROVER | `reconciliation:approve` |
| `period_close:approve` | OWNER, FINANCE_OFFICER, APPROVER | `reconciliation:approve` |
| `period_close:read` | every role that already has `ledger:read` | `reporting:read` |

A plain `ACCOUNTANT` can request a close and watch its controls
evaluate, but can never review or approve one — even their own
(`test_full_close_workflow_across_every_module` proves this with a
real `PermissionDeniedError`, not an assumption). `INVESTOR_REVIEWER`,
`DONOR`, and `REGULATOR` get nothing here, consistent with their
Passport-only model.

## Closed-period protection

Once `approve_close()` succeeds, the accounting period is `LOCKED` via
the Accounting Engine's own, unmodified `lock_period()` — every
existing protection that already implies (no new drafts, no posting,
enforced by `assert_period_open_for_posting`, exercised by every prior
module's own tests) applies with zero new code. Existing posted
journals were always immutable regardless of period status — that
protection is unrelated to this module and untouched.

## Post-close adjustments

**Not implemented — deliberately.** No adjustment policy (which
account, which subsequent period, what authorization threshold) is
defined anywhere in the blueprint or existing modules, and inventing
one here would be inventing accounting policy the build brief
explicitly forbade. Attempting to post into a closed/locked period
today fails with the Accounting Engine's own pre-existing
`PeriodLockedError` — exactly like any other locked period, with no
special-cased adjustment path. If a real adjustment policy is defined
later, it should be built the same way this whole module was: call
`accounting.create_draft_journal`/`post_journal` explicitly, into a
new open period, never by silently reopening a locked one.

## Retained earnings

**Not implemented — deliberately.** Automatically journaling net
income into an equity account at close would require a defined
convention this codebase doesn't have: which account receives it, how
it's identified (by name? by a new `is_retained_earnings` flag on
`Account`?), and what happens if none exists or several do. None of
that is specified anywhere in the blueprint. Per the build brief's own
instruction — "if the starter blueprint does NOT define sufficient
rules for retained earnings, DO NOT invent them" — this module leaves
the Balance Sheet's documented imbalance (see `reporting/README.md`:
it equals the period's unclosed net income) exactly as Reporting
already reports it. Closing a period here means locking it, not
zeroing out its revenue/expense accounts.

## Evidence integration

No new evidence storage. `_check_required_evidence` calls
`EvidenceVault.get_evidence(org_id, evidence_id)` for each caller-named
reference and inspects its actual `status` — `VERIFIED` passes,
`REJECTED` fails outright (never silently treated as valid), anything
else (`UPLOADED`, `INCOMPLETE`, etc.) fails as "not yet verified." A
missing reference (`EvidenceNotFoundError`) is caught and reported as
"not found," not as a crash.

## Reconciliation integration

No reconciliation logic is duplicated. This module only *reads*
`ReconciliationService.list_reconciliations()`/`list_transactions()`
and never calls any of Reconciliation's write methods — it cannot
silently alter a reconciliation's status or match. Fully optional at
construction time (`reconciliation=None` yields a `NOT_APPLICABLE`
finding, never a crash).

## Financial Reporting integration

The `TRIAL_BALANCE_BALANCED` control is the *only* place this module
touches financial figures, and it does so by calling
`ReportingService.get_trial_balance()` — no debit/credit arithmetic is
duplicated here. Income Statement and Balance Sheet are not separately
re-validated as close controls (their liabilities/equity/revenue
figures all derive from the same trial balance this control already
checks) — re-running them would duplicate, not add, a check.

## Audit events

`CLOSE_CHECK_STARTED`, `CLOSE_CHECK_COMPLETED`, `CLOSE_REQUESTED`,
`CLOSE_CONTROL_FAILED`, `CLOSE_REVIEWED`, `CLOSE_APPROVED`,
`CLOSE_REJECTED`, `PERIOD_CLOSED` — all written to the one shared
`asavexa/audit/` trail. **No `PERIOD_LOCKED` event here**: calling
`accounting.lock_period()` already logs that under Accounting's own
`AuditAction`, correctly attributed to the approving actor — duplicating
it would create two audit rows for one real action. **No
`POST_CLOSE_ADJUSTMENT_REQUESTED`**: that capability isn't implemented
(see above).

## Tenant isolation

Enforced by delegation, with zero additional logic: every call this
module makes (`accounting.periods.get`, `reporting.get_trial_balance`,
`reconciliation.list_reconciliations`, `evidence.get_evidence`, and its
own `close_processes` repository) is already strictly `org_id`-scoped
by the module it belongs to. A `PeriodCloseProcess` created for
Organisation A is simply invisible to Organisation B's `org_id` — not
filtered after the fact, never fetched at all. Proven with a real
second organisation in both the unit tests and the end-to-end
integration test.

## Test results

`PYTHONPATH=src python3 -m unittest discover -s tests -v`
→ **198/198 passing** at the time of the cross-module integrity audit
(113 pre-existing when this module was first built + 27
`test_period_close_service.py` + 1 `test_period_close_integration.py`
+ 1 `test_approve_close_re_verifies_readiness_and_catches_a_regression`
added during that audit). Zero existing tests modified, weakened, or
skipped.

## Known limitations

- **Post-close adjustments and retained-earnings automation are not
  implemented** — see the dedicated sections above for exactly why.
- **`RECONCILIATION_EXCEPTIONS` is non-blocking by default** — a
  configuration flag to make it blocking per-organisation does not
  exist yet; today the only lever is whether the caller wires a
  `ReconciliationService` in at all.
- **The reconciliation-to-period link is a date-range heuristic**, not
  a foreign key — see "Close controls" above.
- **No cross-period close** (closing several periods, e.g. a quarter,
  in one operation) — one `PeriodCloseProcess` always covers exactly
  one `AccountingPeriod`, matching Reporting's own single-period
  scoping.
- **API layer untested** — same honest caveat as every prior module:
  this sandbox has no network access to install
  `fastapi`/`sqlalchemy`, so `api/routers/period_close.py` and
  `api/schemas/period_close.py` are syntax-checked but not executed.
  The service layer they call is fully tested (28 tests) against real,
  SQLite-backed Accounting, Reporting, Reconciliation, and Evidence
  instances.

This module is **not** a claim that Asavexa is production-ready for
real period-end close — no post-close adjustment path, no
retained-earnings automation, and an untested API layer all remain
real gaps, stated here rather than implied away.
