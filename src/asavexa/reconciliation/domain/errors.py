"""
Error hierarchy for Reconciliation.

Named errors.py (not exceptions.py) to match the convention already
used by accounting/domain/errors.py, evidence/domain/errors.py, and
identity/domain/errors.py — "architecture consistent with the existing
project" takes precedence over the build brief's suggested filename.
"""


class AsavexaReconciliationError(Exception):
    """Base class for all Reconciliation domain errors."""


class ReconciliationNotFoundError(AsavexaReconciliationError):
    pass


class BankTransactionNotFoundError(AsavexaReconciliationError):
    pass


class BankAccountNotFoundError(AsavexaReconciliationError):
    """The referenced Accounting Engine account does not exist (or is
    not visible) for this organisation. Kept as this module's own error
    type rather than re-raising accounting's AccountNotFoundError, so
    API error-handling stays scoped per module."""


class DuplicateExternalTransactionError(AsavexaReconciliationError):
    """
    Raised when an imported row's dedup hash (org + bank account +
    external ref + date + amount + description) already exists, unless
    the caller explicitly passes allow_duplicate=True. Mirrors
    Evidence's DuplicateEvidenceError — never silently deduplicate,
    always make the caller decide.
    """


class InvalidTransactionStateError(AsavexaReconciliationError):
    """Raised on an illegal BankTransaction status transition."""


class InvalidReconciliationStateError(AsavexaReconciliationError):
    """Raised on an illegal Reconciliation status transition, e.g.
    importing into a non-DRAFT reconciliation, or approving one that
    isn't SUBMITTED."""


class JournalAlreadyMatchedError(AsavexaReconciliationError):
    """Raised when a manual match targets a ledger journal that is
    already matched (and not rejected) against a different transaction
    in the same organisation — one ledger entry cannot prove two
    different bank transactions."""


class UnresolvedTransactionsError(AsavexaReconciliationError):
    """
    Raised when attempting to approve a Reconciliation while one or
    more of its transactions have not reached APPROVED status — the
    blueprint's rule against silently forcing a reconciliation to make
    it "done". Never resolved automatically; someone with
    reconciliation:match / reconciliation:approve must act on each one.
    """


class EmptyReconciliationError(AsavexaReconciliationError):
    """Raised when submitting a Reconciliation with zero transactions."""
