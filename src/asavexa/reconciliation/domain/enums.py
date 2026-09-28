"""
Enumerations for the Reconciliation module.

Signature principle: "Don't just reconcile the number. Prove the match."

Two independent state machines exist here, deliberately:

- `BankTransactionStatus` — the lifecycle of one imported external
  transaction as it moves toward being proven against the ledger. This
  is the chain named in the module's build instructions: IMPORTED ->
  MATCHED -> REVIEW_REQUIRED -> APPROVED -> RECONCILED, plus an explicit
  UNMATCHED/REJECTED branch for exceptions — never an arbitrary
  auto-resolution.
- `ReconciliationStatus` — the outer batch/review workflow (a maker
  prepares it, a different-permissioned checker approves or rejects
  it), analogous to the Accounting Engine's DRAFT -> POSTED but with an
  explicit review step in between, matching this module's maker-checker
  requirement.
"""
from enum import Enum


class BankTransactionStatus(str, Enum):
    IMPORTED = "IMPORTED"                # just landed, not yet matched
    MATCHED = "MATCHED"                  # a specific ledger journal has been proposed/accepted
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # ambiguous (multiple candidates) or flagged for human judgement
    UNMATCHED = "UNMATCHED"              # no ledger candidate found
    APPROVED = "APPROVED"                # a checker has individually approved this line's match
    RECONCILED = "RECONCILED"            # terminal — locked in as part of a finalized Reconciliation
    REJECTED = "REJECTED"                # a checker disagreed with a proposed/manual match


class ReconciliationStatus(str, Enum):
    DRAFT = "DRAFT"            # maker is importing/matching transactions
    SUBMITTED = "SUBMITTED"    # maker is done; awaiting a checker
    RECONCILED = "RECONCILED"  # terminal — checker approved and finalized
    REJECTED = "REJECTED"      # terminal — checker sent it back; rework means a new Reconciliation


class MatchOutcome(str, Enum):
    """The result of running deterministic matching against one
    transaction — never a silent guess, always one of these three."""
    UNIQUE_CANDIDATE = "UNIQUE_CANDIDATE"
    AMBIGUOUS = "AMBIGUOUS"
    NO_CANDIDATE = "NO_CANDIDATE"


class AuditAction(str, Enum):
    RECONCILIATION_CREATED = "RECONCILIATION_CREATED"
    TRANSACTION_IMPORTED = "TRANSACTION_IMPORTED"
    DUPLICATE_IMPORT_REJECTED = "DUPLICATE_IMPORT_REJECTED"
    CANDIDATE_MATCH_GENERATED = "CANDIDATE_MATCH_GENERATED"
    MATCH_ACCEPTED = "MATCH_ACCEPTED"
    MATCH_REJECTED = "MATCH_REJECTED"
    MANUAL_MATCH_PERFORMED = "MANUAL_MATCH_PERFORMED"
    EXCEPTION_CREATED = "EXCEPTION_CREATED"
    TRANSACTION_APPROVED = "TRANSACTION_APPROVED"
    RECONCILIATION_SUBMITTED = "RECONCILIATION_SUBMITTED"
    RECONCILIATION_APPROVED = "RECONCILIATION_APPROVED"
    RECONCILIATION_REJECTED = "RECONCILIATION_REJECTED"
    RECONCILIATION_FINALIZED = "RECONCILIATION_FINALIZED"
    EVIDENCE_LINKED = "EVIDENCE_LINKED"
