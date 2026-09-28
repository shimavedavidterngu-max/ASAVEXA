"""
Pure invariant checks for Reconciliation — no side effects, no storage
dependency, same discipline as accounting/domain/rules.py and
evidence/domain/rules.py.
"""
from __future__ import annotations

from .enums import BankTransactionStatus, ReconciliationStatus
from .errors import InvalidReconciliationStateError, InvalidTransactionStateError

# BankTransaction transitions. RECONCILED is fully terminal — a line
# locked into a finalized Reconciliation is never reopened; correcting
# it means a new Reconciliation superseding this one (see
# Reconciliation.supersedes_reconciliation_id), the same "never
# silently reopen" philosophy the Accounting Engine applies to posted
# journals.
TRANSACTION_TRANSITIONS: dict[BankTransactionStatus, frozenset[BankTransactionStatus]] = {
    BankTransactionStatus.IMPORTED: frozenset({
        BankTransactionStatus.MATCHED, BankTransactionStatus.REVIEW_REQUIRED,
        BankTransactionStatus.UNMATCHED,
    }),
    BankTransactionStatus.MATCHED: frozenset({
        BankTransactionStatus.APPROVED, BankTransactionStatus.REVIEW_REQUIRED,
        BankTransactionStatus.REJECTED,
    }),
    BankTransactionStatus.REVIEW_REQUIRED: frozenset({
        BankTransactionStatus.MATCHED, BankTransactionStatus.UNMATCHED,
    }),
    BankTransactionStatus.UNMATCHED: frozenset({
        BankTransactionStatus.MATCHED, BankTransactionStatus.REVIEW_REQUIRED,
    }),
    BankTransactionStatus.REJECTED: frozenset({
        BankTransactionStatus.REVIEW_REQUIRED,
    }),
    BankTransactionStatus.APPROVED: frozenset({
        BankTransactionStatus.RECONCILED,   # only via Reconciliation approval, not directly
        BankTransactionStatus.REJECTED,     # checker changes their mind before finalization
    }),
    BankTransactionStatus.RECONCILED: frozenset(),  # terminal
}

# Reconciliation (batch) transitions. Both RECONCILED and REJECTED are
# terminal — rework means creating a new Reconciliation, not reopening
# this one (see errors.py / models.py docstrings).
RECONCILIATION_TRANSITIONS: dict[ReconciliationStatus, frozenset[ReconciliationStatus]] = {
    ReconciliationStatus.DRAFT: frozenset({ReconciliationStatus.SUBMITTED}),
    ReconciliationStatus.SUBMITTED: frozenset({
        ReconciliationStatus.RECONCILED, ReconciliationStatus.REJECTED,
    }),
    ReconciliationStatus.RECONCILED: frozenset(),
    ReconciliationStatus.REJECTED: frozenset(),
}


def assert_transaction_transition_allowed(
    current: BankTransactionStatus, new: BankTransactionStatus
) -> None:
    if new not in TRANSACTION_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransactionStateError(
            f"Cannot move a bank transaction from {current.value} to {new.value}."
        )


def assert_reconciliation_transition_allowed(
    current: ReconciliationStatus, new: ReconciliationStatus
) -> None:
    if new not in RECONCILIATION_TRANSITIONS.get(current, frozenset()):
        raise InvalidReconciliationStateError(
            f"Cannot move a reconciliation from {current.value} to {new.value}."
        )
