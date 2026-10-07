"""Error hierarchy for Financial Reporting. Named errors.py, matching
the convention already used by accounting/, evidence/, identity/, and
reconciliation/'s domain packages."""


class AsavexaReportingError(Exception):
    """Base class for all Reporting domain errors."""


class ReportingPeriodNotFoundError(AsavexaReportingError):
    """Raised when the given (org_id, period_id) does not resolve to a
    real AccountingPeriod. This is also how an invalid/foreign org_id
    surfaces — a period never belongs to an organisation that doesn't
    exist, so there is no separate 'organisation not found' check here;
    Reporting does not own organisation identity and does not import
    IdentityService to verify it independently."""


class ReportingAccountNotFoundError(AsavexaReportingError):
    """Raised by trace_line() when the given account_id does not exist
    for this organisation."""


class UnknownReportTypeError(AsavexaReportingError):
    """Raised by the generic generate(report_type, ...) dispatcher for
    anything not in domain.enums.ReportType."""


class UnsupportedAccountClassificationError(AsavexaReportingError):
    """
    Defensive-only: AccountType is a closed, exhaustive enum
    (ASSET/LIABILITY/EQUITY/REVENUE/EXPENSE) enforced by the Accounting
    Engine itself, so every account Reporting ever sees already has one
    of these five types — this branch should be unreachable in
    practice. It exists so a future AccountType addition fails loudly
    here instead of an account silently vanishing from every statement.
    """


class ReconciliationNotConfiguredError(AsavexaReportingError):
    """Raised by get_reconciliation_summary when this ReportingService
    instance was constructed without a ReconciliationService — the
    integration is optional, not assumed."""


class EvidenceNotConfiguredError(AsavexaReportingError):
    """Raised by get_evidence_completeness when this ReportingService
    instance was constructed without an EvidenceVault — the
    integration is optional, not assumed (same pattern as
    ReconciliationNotConfiguredError above)."""
