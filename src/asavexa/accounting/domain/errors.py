"""
Error hierarchy for the Asavexa Accounting Engine.

Every error here maps to a specific Non-Negotiable Development Rule in the
ASAVEXA Master Blueprint (Section 7). The API layer is responsible for
translating these into clear, non-hidden error responses — the blueprint's
Error Handling Rule: "never hide errors ... explain the problem, preserve
the original record, provide a recovery path."
"""


class AsavexaAccountingError(Exception):
    """Base class for all accounting-engine domain errors."""


class AccountNotFoundError(AsavexaAccountingError):
    pass


class InactiveAccountError(AsavexaAccountingError):
    pass


class PeriodNotFoundError(AsavexaAccountingError):
    pass


class PeriodLockedError(AsavexaAccountingError):
    """Raised when attempting to post/reverse a journal dated in a
    locked or closed period."""


class EmptyJournalError(AsavexaAccountingError):
    """A journal must have at least two lines to be a valid double entry."""


class UnbalancedJournalError(AsavexaAccountingError):
    """
    Rule: "Debits must equal credits for every balanced journal."
    Raised whenever total debits != total credits, to the currency's
    minor unit.
    """


class InvalidLineAmountError(AsavexaAccountingError):
    """A line must have exactly one of debit/credit non-zero, and neither
    may be negative."""


class CurrencyMismatchError(AsavexaAccountingError):
    """All lines in a single journal must share one currency in this
    version of the engine (see README — multi-currency conversion is
    explicitly out of scope until real FX-rate sourcing is designed)."""


class JournalNotFoundError(AsavexaAccountingError):
    pass


class InvalidJournalStateError(AsavexaAccountingError):
    """Raised for illegal state transitions, e.g. posting an already-
    posted or already-reversed journal."""


class ImmutableJournalError(AsavexaAccountingError):
    """
    Rule: "Posted journal entries are immutable ... corrections use
    reversals or controlled adjustments rather than silent edits."
    Raised on any attempt to edit or delete a POSTED or REVERSED journal.
    """
