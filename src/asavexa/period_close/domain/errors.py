"""Error hierarchy for Period Close & Financial Controls. Named
errors.py, matching every other module's domain package convention."""


class AsavexaPeriodCloseError(Exception):
    """Base class for all Period Close domain errors."""


class PeriodCloseProcessNotFoundError(AsavexaPeriodCloseError):
    pass


class PeriodNotFoundError(AsavexaPeriodCloseError):
    """The given (org_id, period_id) does not resolve to a real
    AccountingPeriod. Also how a foreign/invalid org_id is caught — a
    period never belongs to an organisation that doesn't exist. This
    module does not own period identity and does not duplicate
    Accounting's own PeriodNotFoundError type, keeping API error
    handling scoped per module (same precedent as Reporting's
    ReportingPeriodNotFoundError and Reconciliation's
    BankAccountNotFoundError)."""


class CloseAlreadyInProgressError(AsavexaPeriodCloseError):
    """Raised when requesting a close for a period that already has a
    non-terminal PeriodCloseProcess (REQUESTED, READY_FOR_CLOSE, or
    CONTROLS_FAILED) — only one active close workflow per period at a
    time; rework after REJECTED means a new process
    (`supersedes_close_process_id`), never two live ones."""


class InvalidCloseStateError(AsavexaPeriodCloseError):
    """Raised on an illegal PeriodCloseProcess status transition."""


class CloseNotReadyError(AsavexaPeriodCloseError):
    """Raised by approve_close() when the process is not currently
    READY_FOR_CLOSE — e.g. still REQUESTED without having been
    reviewed, or sitting in CONTROLS_FAILED."""


class NotReviewedError(AsavexaPeriodCloseError):
    """Raised by approve_close() when no review has been recorded yet
    — review and approval are separate, both-required steps."""
