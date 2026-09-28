# Reconciliation

**"Don't just reconcile the number. Prove the match."**

Connects: **External Transaction → Matching Decision → Ledger (read-only) → Evidence (opaque reference) → Review/Approval → shared Audit Trail.**

## What this module is

- **`Reconciliation`** — a batch: one bank account, one statement period, prepared by a maker and finalized by a checker. `DRAFT → SUBMITTED → RECONCILED | REJECTED`. Both `RECONCILED` and `REJECTED` are terminal; rework means creating a *new* `Reconciliation` (`supersedes_reconciliation_id`), never reopening the old one.
- **`BankTransaction`** — one imported external transaction. Never a journal entry — it only ever points at one via `matched_journal_id`. `IMPORTED → MATCHED → REVIEW_REQUIRED / UNMATCHED / REJECTED → APPROVED → RECONCILED`.
- **Matching decision** — not persisted as a separate row; it's the `match_rule` + `match_reason` + `match_history` on the `BankTransaction` itself, produced by `domain/matching.py`. Every match names its rule (`EXACT_AMOUNT_AND_DATE_WITHIN_TOLERANCE` or `MANUAL_OVERRIDE`) — never just "Matched" with no explanation.
- **Exception** — not a separate class. An exception is simply a `BankTransaction` sitting in `REVIEW_REQUIRED` or `UNMATCHED` — first-class, visible states, not a hidden flag.

This mirrors the Accounting Engine and Evidence Vault's own domain/repository/services shape — no flat file layout, no new architecture invented for this module.

## Integration boundaries (what this module does NOT do)

- **Never writes to the Accounting Engine.** Only reads `accounts.get()`, `journals.get()`, and `get_ledger()` — no journal is ever created, posted, or reversed here. Proven directly by `test_accounting_engine_state_is_unchanged_by_reconciliation`.
- **No dependency on EvidenceVault or IdentityService.** Evidence linkage is one opaque id (`Reconciliation.evidence_ref`), set by `attach_evidence` — the caller uploads to the Evidence Vault first and hands back the id, exactly like `Journal.evidence_ref` is set by the caller, not by AccountingEngine calling into EvidenceVault. Permission checks are not performed inside this module at all — every service method trusts an already-authorized `actor: str`, exactly like Accounting and Evidence. RBAC lives only at the API boundary (`api/deps.py::require_permission`).
- **No second audit system.** Writes to the one shared `asavexa/audit/` trail, using its own local `AuditAction` string-enum — the same pattern Accounting, Identity, and Evidence already use (a shared *store*, per-module *vocabulary*).
- **No second permission system.** RBAC is five new permission constants added to the existing single registry, `identity/domain/permissions.py` — see that file's docstring for exactly which roles get which and why.

## Matching

Deterministic and explainable — never AI, never a silent guess:

1. A ledger candidate qualifies only if it shows the **exact same debit/credit shape** on the bank account (not "similar" — equal, to the cent) and falls within a **date tolerance** (default 3 days) of the statement date.
2. A journal already claimed by another live match (`MATCHED`/`APPROVED`/`RECONCILED`) is excluded — two bank transactions cannot both "prove" the same ledger entry.
3. **Zero candidates → `UNMATCHED`.** **Exactly one → `MATCHED`**, with the reason and rule code recorded. **Two or more → `REVIEW_REQUIRED`** — never picked arbitrarily.
4. A human can always override via `manual_match` — even a mismatched amount is *permitted* (a human explicitly decided), but the mismatch is written into `match_reason` verbatim, never silently treated as equal.

## Duplicate import control

`dedup_hash = sha256(org_id, bank_account_id, external_ref, date, debit, credit, normalized description)`, unique per `(org_id, bank_account_id)` in both the SQLite and PostgreSQL schemas. A row whose hash already exists is rejected outright — the whole import call fails before anything is written, so a batch is never half-applied.

## Maker-checker

Reuses `identity/domain/permissions.py` — no separate approval framework:

| Permission | Who has it | Action it gates |
|---|---|---|
| `reconciliation:create` | OWNER, ACCOUNTANT, FINANCE_OFFICER | create a reconciliation, submit it, attach evidence |
| `reconciliation:import` | OWNER, ACCOUNTANT, FINANCE_OFFICER | import bank transactions |
| `reconciliation:match` | OWNER, ACCOUNTANT, FINANCE_OFFICER | manual match |
| `reconciliation:approve` | OWNER, FINANCE_OFFICER, APPROVER | reject a match, approve a transaction, approve/reject the reconciliation |
| `reconciliation:read` | all internal roles (not INVESTOR_REVIEWER/DONOR/REGULATOR — Passport-only by existing design) | read anything |

A plain `ACCOUNTANT` can prepare a reconciliation end-to-end — import, match, attach evidence, submit — and is refused at `reconciliation:approve` every time, even for their own work (`test_same_actor_cannot_prepare_and_approve_their_own_reconciliation`). `approve_reconciliation` additionally requires every transaction in the batch to already be individually `APPROVED` — it will not finalize over unresolved exceptions (`UnresolvedTransactionsError`).

## State machines

Both live in `domain/rules.py` as explicit transition tables — a transition not in the table raises `InvalidTransactionStateError` / `InvalidReconciliationStateError`. No client can set a status field directly; the API only exposes the named actions (`submit`, `approve`, `reject`, `manual-match`, ...), never a raw PATCH-status endpoint. `RECONCILED` is terminal for both the batch and every one of its lines.

## Known limitations

- No period-scoped candidate filtering — `get_ledger` is called without a `period_id`, so matching considers the account's entire posted history, not just the statement's date range (correct today because the date-tolerance filter already excludes distant entries; would need tightening if reconciliation windows grow much larger than the tolerance).
- No bulk "approve all matched transactions" convenience — each is approved individually, by design (a checker should look at each one).
- Evidence-before-approval is a **caller-level policy**, not enforced inside this module (see "Integration boundaries" above) — the demo in `tests/test_reconciliation_integration.py` shows the checker verifying evidence status before approving, but nothing stops an API caller from skipping that check unless a future policy layer enforces it.
