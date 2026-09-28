# Financial Reporting

**"Don't just report the number. Prove it."**

A **read/derivation layer** over the Accounting Engine. It creates
nothing, posts nothing, and cannot alter a balance — every number here
is computed fresh, on the spot, from `AccountingEngine.get_trial_balance()`
and `AccountingEngine.get_ledger()`.

## Architecture — why there is no `reporting/repository/`

Every other module (`accounting`, `identity`, `evidence`,
`reconciliation`) has a `domain/ · repository/ · services/` shape
because each of them owns data that must persist between calls: a
posted journal, a membership, an uploaded file, an imported bank row.
Reporting owns none of that. A report is a *view*, not a *record* — so
this module has `domain/` (report/line dataclasses, the `ReportType`
enum, calculation rules, errors) and `services/` (`ReportingService`),
and nothing to store. This isn't a shortcut; the build brief itself
asked to "prefer a derived/read model rather than storing duplicate
accounting data," and there is no meaningful entity here to duplicate.

The one thing this module *doesn't* skip: **the shared audit trail**.
Every successful report generation logs one `REPORT_GENERATED` event
(org, actor, report type, top-line totals only — never the full line
dump); a failed one logs `REPORT_GENERATION_FAILED` and still raises.

## Supported reports

- **Trial Balance** — every account with activity in the period, its
  debit/credit totals, and `is_balanced` (from
  `AccountingEngine.get_trial_balance` directly — never recomputed
  differently, never forced to `True`).
- **Income Statement** — `REVENUE` and `EXPENSE` accounts only, each
  converted to its normal-balance sign (see "Calculation rules"
  below), with `net_income = total_revenue - total_expenses`.
- **Balance Sheet** — `ASSET`, `LIABILITY`, and `EQUITY` accounts,
  `accounting_equation_holds` (`assets == liabilities + equity`), and
  an `imbalance_amount` that is **exposed, never hidden**, when it
  doesn't.
- **General Ledger** — one or more accounts' full posted line history
  (optionally scoped to a period), each with a running balance,
  wrapped with account metadata.

## Calculation rules

`AccountingEngine.get_trial_balance()` gives raw `debit_total`/
`credit_total` per account — it imposes no normal-balance sign
convention, only that debits equal credits per journal.
`domain/rules.py::normal_balance_amount` applies the standard
convention implied by `AccountType`'s five values:

| Type | Normal balance | Amount formula |
|---|---|---|
| ASSET, EXPENSE | debit | `debit_total - credit_total` |
| LIABILITY, EQUITY, REVENUE | credit | `credit_total - debit_total` |

This is not a textbook formula imposed blindly — it's the only
convention consistent with what those five `AccountType` values are
*for*, so it fully respects the Accounting Engine's own design rather
than inventing a parallel one.

**Why the Balance Sheet often won't balance in this starter, and why
that's correct:** this Accounting Engine has no period-close /
retained-earnings automation. By the mechanics of double-entry
bookkeeping, `Assets - Liabilities - Equity` always equals
`Revenue - Expense` (net income) for the period, until that income is
formally closed into an equity account. So `imbalance_amount` on an
unclosed period is expected to equal that period's net income exactly
— proven directly by
`test_balance_sheet_imbalance_equals_unclosed_net_income`. This is
Reporting doing its job (exposing the true state of the ledger), not a
bug. A Balance Sheet generated for a period with only capital/loan
activity (no revenue or expense) balances exactly, as shown by
`test_balance_sheet_holds_with_pure_capital_and_loan_activity`.

## Period handling

Reports are always scoped to exactly one `AccountingPeriod` — Trial
Balance, Income Statement, and Balance Sheet all require a
`period_id` and resolve it via `accounting.periods.get(org_id,
period_id)`, raising `ReportingPeriodNotFoundError` if it doesn't
exist for that organisation (which is also how a foreign/invalid
`org_id` is caught — a period never belongs to an organisation that
doesn't exist, so there is no separate "organisation not found" check,
and no import of `IdentityService` into this module to perform one).
The General Ledger's `period_id` is optional, matching
`AccountingEngine.get_ledger()`'s own optional `period_id` — omitting
it returns an account's entire posted history. No independent period
system was created; this module has no period concept of its own at
all.

## Provenance / traceability

Every report line carries `account_id`, `account_code`, `account_name`,
and `account_type`. For the underlying journal-level evidence behind
any one number, call `ReportingService.trace_line(org_id, account_id,
period_id)` — a thin, named wrapper over `AccountingEngine.get_ledger()`
that returns the exact posted entries, each with its `journal_id`,
`journal_number`, `evidence_ref`, and `transaction_ref`. Provenance is
one explicit call away, not embedded in every summary line by
default — a Trial Balance with fifty accounts would otherwise have to
pull the full ledger for all fifty on every generation just in case
someone wanted to drill into one of them.

## Evidence integration

No dependency on `EvidenceVault` at all. Each ledger entry returned by
`get_ledger()` (and therefore by `trace_line()`) already carries the
posting journal's `evidence_ref` — Reporting surfaces it as-is; the
caller resolves it against the Evidence Vault themselves, exactly like
every prior cross-module test in this codebase has done. Reporting
does not claim a number is "proven" merely because a file exists, and
does not require one to exist before generating a report — evidence
absence is visible (the field is `None`/`MISSING` per Evidence's own
sentinel), never fabricated or hidden.

## Reconciliation integration

Fully optional, read-only, and additive: `ReportingService` may be
constructed with a `reconciliation=` argument (a `ReconciliationService`
instance). `get_reconciliation_summary(org_id, bank_account_id)` then
tallies that account's `BankTransaction` statuses (`RECONCILED` /
outstanding / exception) via `reconciliation.transactions.list_for_account(...)`
— a plain read of an already-public repository attribute, no new method
added to `ReconciliationService`. Without a `reconciliation=` argument,
calling this method raises `ReconciliationNotConfiguredError` rather
than silently returning nothing. Nothing about reconciliation status
ever changes a report figure — proven directly by
`test_full_reporting_flow_with_provenance_reconciliation_and_audit`,
which regenerates the Trial Balance after pulling a reconciliation
summary and asserts the totals are identical.

## Permissions

One new permission, added to the existing registry
(`identity/domain/permissions.py`), not a second one:

| Permission | Roles | Why |
|---|---|---|
| `reporting:read` | every role that already has `ledger:read` (OWNER, ADMINISTRATOR, ACCOUNTANT, FINANCE_OFFICER, APPROVER, REVIEWER, MANAGER, AUDITOR, EXTERNAL_AUDITOR, READ_ONLY) | a report is a derived view of the same ledger data `ledger:read` already exposes — the same trust boundary applies |

**No separate `reporting:generate` permission.** In this architecture,
"generating" a report and "reading" it are the exact same action — the
result is never cached or persisted, so there is nothing distinct for
"generate" to create that "read" would later view. Adding a second
permission that always gates identically to the first would be
inventing a distinction the implementation doesn't have. If snapshots
or export are added later and a real distinction emerges, split it
then. `INVESTOR_REVIEWER`, `DONOR`, and `REGULATOR` get nothing here,
consistent with their Passport-only access model established when
Identity was built.

## Tenant isolation

Enforced entirely by delegation, with zero additional logic in this
module: every accounting call Reporting makes
(`accounting.accounts.get/list_for_org`, `accounting.periods.get`,
`accounting.get_ledger`, `accounting.get_trial_balance`) is already
strictly `org_id`-scoped by the Accounting Engine's own repositories.
A period, account, or ledger entry belonging to another organisation
is simply invisible — not filtered after the fact, never fetched at
all. Proven directly by cross-tenant tests using a real second
organisation, not a mocked one.

## Audit events

`REPORT_GENERATED` (on every successful call to any of the four report
methods) and `REPORT_GENERATION_FAILED` (logged before the exception
is re-raised, never swallowing it). No `REPORT_REGENERATED`,
`REPORT_FINALIZED`, or `REPORT_EXPORTED` — none of those concepts exist
in a purely derived, unpersisted, unexported reporting model; adding
audit actions for capabilities that don't exist would be misleading,
not thorough.

## Known limitations

- **No cross-period reports.** A "Q1" statement spanning three monthly
  `AccountingPeriod`s isn't supported — reports are scoped to exactly
  one period, matching `get_trial_balance()`'s own scoping. Combining
  periods would need a small, explicit multi-period aggregation added
  here later; it should not require changing the Accounting Engine.
- **No period-close / retained-earnings rollup** (inherited from the
  Accounting Engine — see "Calculation rules" above for why this is
  visible, not hidden).
- **Export was deliberately not built.** JSON/CSV/PDF export was in
  scope for consideration, not for delivery in this pass — every
  report here is already a plain dataclass, trivially serializable by
  a caller; a dedicated export format can be layered on without
  touching the reporting domain.
- **API layer untested** — same honest caveat as every prior module:
  this sandbox has no network access to install `fastapi`/`sqlalchemy`,
  so `api/routers/reporting.py` and `api/schemas/reporting.py` are
  syntax-checked but not executed. The service layer they call is
  fully tested (26 tests) against a real, SQLite-backed
  `AccountingEngine`.

## Test results

`PYTHONPATH=src python3 -m unittest discover -s tests -v`
→ **113/113 passing** (87 pre-existing + 25 `test_reporting_service.py`
+ 1 `test_reporting_integration.py`). Zero existing tests modified or
weakened.

One pre-existing bug was found and fixed while building this module's
provenance tracing: `accounting/repository/sqlite_repository.py`'s
`JournalRepository.update()` (and its SQLAlchemy equivalent) never
actually persisted `evidence_ref`/`transaction_ref`, despite the
`Journal` model documenting them as settable after creation and its own
docstring claiming to handle "metadata." This is a storage-adapter
fix — debit/credit rules, immutability, period locks, and
posting/reversal behavior are all untouched; see the top-level
README's "Files modified" for the exact diff.
