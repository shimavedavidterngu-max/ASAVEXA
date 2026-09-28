"""
Enumerations for Financial Reporting.

Signature principle: "Don't just report the number. Prove it."
"""
from enum import Enum


class ReportType(str, Enum):
    TRIAL_BALANCE = "TRIAL_BALANCE"
    INCOME_STATEMENT = "INCOME_STATEMENT"
    BALANCE_SHEET = "BALANCE_SHEET"
    GENERAL_LEDGER = "GENERAL_LEDGER"


class AuditAction(str, Enum):
    REPORT_GENERATED = "REPORT_GENERATED"
    REPORT_GENERATION_FAILED = "REPORT_GENERATION_FAILED"
    # No REPORT_REGENERATED / REPORT_FINALIZED / REPORT_EXPORTED: this
    # module has no persisted report to regenerate-from, finalize, or
    # export (see README "Architecture" — reports are always freshly
    # derived). Every call that succeeds logs REPORT_GENERATED, whether
    # it is the first time that org/period/type combination was asked
    # for or the hundredth.
