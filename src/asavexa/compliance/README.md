# Controls & Compliance / Audit Workspace

**"Don't just claim compliance. Prove the control."**

An orchestration/assessment layer over the six other modules. It defines no accounting rules, stores no evidence, matches no bank transactions, computes no financial statements, and writes to no audit trail of its own. It makes no regulatory claims — no "IFRS compliant", no "SOX compliant" — anywhere in this codebase.

This document reflects the module **after a full audit and hardening pass** (see "Audit history" at the bottom) — every behaviour described here has been verified against the actual code, not just designed.

---

## Architecture: request → persistence → response

```
HTTP request
  → api/routers/compliance.py           (path + method + Pydantic body)
      → api/deps.py::require_permission  (the ONLY enforcement point —
                                           resolves the session, looks up
                                           the caller's role in the
                                           session's org, checks the one
                                           permission this route declared)
          → ComplianceService method     (compliance/services/service.py —
                                           takes a plain actor: str,
                                           performs NO permission checks
                                           of its own)
              → domain/rules.py           (pure transition-table checks —
                                           InvalidFindingStateError /
                                           InvalidRemediationStateError on
                                           violation)
              → repository Protocol       (compliance/repository/interfaces.py —
                                           org_id-scoped get/create/update/list)
                  → SQLite (tests/dev) or SQLAlchemy/Postgres (production)
                      → persistence
      ← Pydantic response schema (api/schemas/compliance.py)
```

**Where each responsibility actually lives:**

| Responsibility | Lives in |
|---|---|
| HTTP routing, request/response shape | `api/routers/compliance.py`, `api/schemas/compliance.py` |
| **Authorization** (the only place permissions are checked) | `api/deps.py::require_permission`, called once per route via `Depends(...)` |
| Domain rules (valid state transitions) | `compliance/domain/rules.py` |
| Business orchestration, audit logging | `compliance/services/service.py` |
| Persistence, tenant scoping on reads | `compliance/repository/{interfaces,sqlite_repository}.py`, `api/db/compliance_{models,sqlalchemy_repository}.py` |
| Cross-module reads (never writes) | `AccountingEngine`, `ReportingService`, `ReconciliationService`, `EvidenceVault`, `PeriodCloseService` — all optional except Accounting/Reporting |

`ComplianceService` performs **zero permission checks**. Every method takes a plain `actor: str` and trusts the caller. This is deliberate and consistent with every other module in this codebase (Reconciliation, Period Close) — authorization is the API layer's job, exactly once, via `require_permission`.

---

## Finding lifecycle (verified)

```
OPEN ──────────────► UNDER_REVIEW ──┬──► REMEDIATION_REQUIRED ──► RESOLVED ──┬──► VERIFIED ──► CLOSED
                          ▲          │                                ▲       │
                          │          └──► RESOLVED (false positive,   │       └──► REMEDIATION_REQUIRED
                          │               reason required)            │            (verifier rejects)
                          └───────────────────────────────────────────┘
                            (reviewer sends back for more information)

CLOSED ──[explicit reopen_finding(reason), bypasses the table]──► OPEN
```

Every arrow above is a **named service method** (`start_review`, `mark_remediation_required`, `mark_resolved_without_remediation`, `send_back_to_open`, `complete_remediation` → auto-transitions to `RESOLVED`, `verify_remediation` → auto-transitions to `VERIFIED`, `reject_remediation` → auto-transitions back to `REMEDIATION_REQUIRED`, `close_finding`). There is **no method that accepts an arbitrary target status** — a client cannot submit `status="CLOSED"` through any route; every transition is checked against `domain/rules.py::FINDING_TRANSITIONS` before being written, and an illegal one raises `InvalidFindingStateError` without touching the repository.

`CLOSED` is the only terminal state reachable through the ordinary table. Reopening it is `reopen_finding(org_id, finding_id, actor, reason)` — a separate method that intentionally is **not** a row in `FINDING_TRANSITIONS`, requires a reason, and logs its own distinct `FINDING_REOPENED` event.

**Remediation lifecycle** (verified): `PLANNED → IN_PROGRESS → COMPLETED → VERIFIED` (terminal), with `COMPLETED → IN_PROGRESS` as the verifier's rejection path. Every transition here is likewise a named method, checked against `domain/rules.py::REMEDIATION_TRANSITIONS`.

---

## Permission matrix (verified against `identity/domain/permissions.py`)

| Role | control:read | control:manage | control:execute | finding:manage | finding:remediate | finding:verify |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| OWNER | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| ADMINISTRATOR | ✓ | ✓ | | ✓ | | |
| ACCOUNTANT | ✓ | | ✓ | | ✓ | |
| FINANCE_OFFICER | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| APPROVER | ✓ | | ✓ | | | ✓ |
| REVIEWER / MANAGER / AUDITOR / EXTERNAL_AUDITOR / READ_ONLY | ✓ | | | | | |
| INVESTOR_REVIEWER / DONOR / REGULATOR | | | | | | |

Five independent capabilities, never combined on one endpoint:
- **`control:manage`** governs the control *library* (define/deactivate/seed) — separate from *running* one.
- **`control:execute`** runs or reviews an execution.
- **`finding:manage`** triages a finding (review, send-back, mark-remediation-required, resolve-without-remediation, reopen, and manually opening a finding from a WARNING/REQUIRES_REVIEW execution — itself a triage judgement, not a re-execution).
- **`finding:remediate`** does the fix. **`finding:verify`** independently confirms it. These are held by disjoint role sets by default (`ACCOUNTANT` has the former, `APPROVER` the latter — proven with real `PermissionDeniedError`s in `tests/test_compliance_permissions.py` and `tests/test_compliance_integration.py`, not asserted from the registry alone).

There is deliberately no sixth `finding:read` — reading findings/executions/remediations is covered by `control:read`.

---

## API endpoints

| Method | Path | Permission |
|---|---|---|
| POST | `/compliance/controls` | `control:manage` |
| POST | `/compliance/controls/seed-standard` | `control:manage` |
| POST | `/compliance/controls/{id}/deactivate` | `control:manage` |
| GET | `/compliance/controls`, `/compliance/controls/{id}` | `control:read` |
| POST | `/compliance/controls/{id}/execute` | `control:execute` |
| POST | `/compliance/executions/{id}/review` | `control:execute` |
| GET | `/compliance/executions`, `/compliance/executions/{id}` | `control:read` |
| POST | `/compliance/executions/{id}/create-finding` | `finding:manage` |
| GET | `/compliance/findings`, `/compliance/findings/{id}` | `control:read` |
| POST | `/compliance/findings/{id}/start-review` | `finding:manage` |
| POST | `/compliance/findings/{id}/send-back-to-open` | `finding:manage` |
| POST | `/compliance/findings/{id}/mark-remediation-required` | `finding:manage` |
| POST | `/compliance/findings/{id}/mark-resolved-without-remediation` | `finding:manage` |
| POST | `/compliance/findings/{id}/reopen` | `finding:manage` |
| POST | `/compliance/findings/{id}/remediations` | `finding:remediate` |
| GET | `/compliance/remediations/{id}` | `control:read` |
| POST | `/compliance/remediations/{id}/start`, `/complete` | `finding:remediate` |
| POST | `/compliance/remediations/{id}/verify`, `/reject` | `finding:verify` |
| POST | `/compliance/findings/{id}/close` | `finding:verify` |

Every mutating route resolves `org_id` from the session (`get_current_org`), never from a client-supplied field — the same pattern as every other module's router.

---

## Built-in controls (the library)

Nine standard controls, seeded via `seed_standard_controls()` (idempotent — matched by `code`), each calling exactly one authoritative module and never recomputing its logic:

| Code | Domain | Calls into |
|---|---|---|
| ACC-001 | Accounting | `ReportingService.get_trial_balance` |
| ACC-002 | Accounting | `AccountingEngine.journals.list_for_org(status=DRAFT)` |
| ACC-003 | Accounting | `AccountingEngine.periods.get` |
| REC-001 | Reconciliation | `ReconciliationService.list_reconciliations` / `list_transactions` |
| EVI-001 | Evidence | `EvidenceVault.get_evidence` (caller-designated references only) |
| EVI-002 | Evidence | `EvidenceVault.get_status_for_reference` |
| REP-001 | Reporting | `ReportingService.get_trial_balance` + `trace_line` |
| CLS-001 | Period Close | `PeriodCloseService.check_close_readiness` |
| CLS-002 | Period Close | `AccountingEngine.periods.get` |

`check_key` selects one of nine fixed Python methods on `ComplianceService` — there is no rule language, no generic engine, and no way to define a control whose logic isn't one of these nine (or a future addition to the same fixed registry).

A `ControlExecution`'s `result`/`explanation`/`reference` are set once at creation and **never edited** — the repository's `update()` only ever touches `reviewed_by`/`reviewed_at`/`finding_id`. Re-evaluating a control after fixing the underlying issue creates a **new** `ControlExecution`; the original `FAIL` record is untouched (proven by `test_control_never_silently_converts_fail_to_pass`).

A `FAIL` result **always** creates a `Finding` automatically. A `WARNING` or `REQUIRES_REVIEW` result does not — a `finding:manage` holder may call `create_finding_from_execution` explicitly if they judge it worth tracking. `PASS` and `NOT_APPLICABLE` results cannot have a finding created against them at all (`CannotCreateFindingForResultError`) — a finding documents a problem, and neither of those describes one.

---

## Tenant isolation

**Enforced at two layers, verified independently:**

1. **Repository reads** — every `get`/`list_for_*` method takes `org_id` and includes it in the SQL `WHERE` clause (all 11 read queries checked directly against the source). A record belonging to another organisation is never fetched, not filtered out afterward.
2. **Service layer** — every public method takes `org_id` explicitly and passes it straight through to the repository; there is no method that accepts a bare record id without an org_id to scope it.

**One documented exception, consistent with the rest of this codebase**: repository `update()` methods do **not** re-filter by `org_id` in their `WHERE` clause (they match on `id` alone). This is safe because the service layer only ever calls `update()` with an object obtained from `get(org_id, id)` in the same operation — which already returned `None` (raising a `*NotFoundError`) if the id belonged to a different organisation. This is the identical pattern used by `accounting.repository.sqlite_repository.JournalRepository`, `evidence.repository.sqlite_repository`, and `reconciliation.repository.sqlite_repository` — verified directly against their source during this audit, not assumed. It is not a Compliance-specific gap, and was deliberately left unchanged rather than "fixed" in a way that would diverge from established precedent.

Proven with tests using a real second organisation (not mocked) for every operation: read a control, execute a control, read/modify/reopen a finding, create a finding against another org's execution, remediate another org's finding, and verify another org's remediation — plus a repository-level test calling `get()` directly (bypassing the service) to confirm isolation holds below the service layer too.

---

## Audit events (verified complete)

| Event | Logged by |
|---|---|
| `CONTROL_DEFINED` | `define_control` |
| `CONTROL_DEACTIVATED` | `deactivate_control` |
| `CONTROL_EXECUTED` | `execute_control` (carries the result — no separate PASS/FAIL events) |
| `CONTROL_REVIEWED` | `review_execution` |
| `FINDING_CREATED` | `execute_control` (auto, on FAIL) or `create_finding_from_execution` (manual) |
| `FINDING_STATUS_CHANGED` | every named finding transition (carries `from`/`to`) |
| `FINDING_REOPENED` | `reopen_finding` |
| `REMEDIATION_CREATED` | `create_remediation` |
| `REMEDIATION_STARTED` | `start_remediation` |
| `REMEDIATION_COMPLETED` | `complete_remediation` |
| `REMEDIATION_REJECTED` | `reject_remediation` |
| `REMEDIATION_VERIFIED` | `verify_remediation` |
| `FINDING_CLOSED` | `close_finding` |

`REMEDIATION_STARTED` and `REMEDIATION_REJECTED` were **added during this audit** — both operations previously executed correctly but left no independent audit trace (see "Audit history" below). Every event carries `org_id`, `actor`, `timestamp`, `action`, and `entity_id`; state-changing events additionally carry `previous`/`new` status via `new_value={"from": ..., "to": ...}` where a transition is involved.

Audit immutability: `AuditRepository`'s Protocol exposes only `record()` and read methods — no `update`/`delete` exists anywhere in its interface or either implementation (verified by grepping the entire codebase for `UPDATE audit_events`/`DELETE FROM audit_events`: zero matches). This is a structural property of the shared `asavexa/audit/` module, not something Compliance adds.

---

## Known limitations

- **API layer untested end-to-end** — same honest caveat as every other module: this sandbox has no network access to install `fastapi`/`sqlalchemy`. Every router/schema file is syntax-checked (`py_compile`) but not executed. The service layer they call is fully tested (52 tests) against real, SQLite-backed collaborators.
- **No generic rule engine** — deliberately. Adding a new control type requires a new Python method and a `_check_registry` entry, not a configuration language.
- **`REQUIRED_EVIDENCE`-style checks trust caller-designated references only** — there is no automatic discovery of "what evidence should this control require."
- **No bulk/scheduled execution** — `frequency` on a `ControlDefinition` is descriptive metadata only; nothing runs a control automatically.

## Audit history

This module was built, then subjected to a dedicated audit-and-harden pass before any further module was started. That pass found and fixed six genuine defects (two missing audit events, one missing state guard, one schema/router inconsistency, one missing production-schema table, one stale docstring) and added 13 tests that did not exist before, including the module's first cross-module integration test tracing a full WARNING→finding→remediation→verification chain against real `IdentityService` permission checks. See the git history / conversation record for the itemised list; this README describes the module's state *after* that pass.

## Test results

`PYTHONPATH=src python3 -m unittest discover -s tests -v`
→ **197/197 passing** (185 pre-audit + 12 new in this pass). Zero existing tests modified, weakened, or removed.
