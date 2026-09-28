"""
Enumerations for Period Close & Financial Controls.

Signature principle: "Don't just close the period. Prove that it was
properly closed."

Two separate concerns, two separate enums:

- `PeriodCloseStatus` — this module's OWN workflow state (a
  `PeriodCloseProcess` record: who requested, who reviewed, who
  approved). This is a governance concept, not an accounting one.
- The actual accounting enforcement — "can anyone still post into this
  period" — is never reimplemented here. It lives entirely in
  `accounting.domain.enums.PeriodStatus` (OPEN/LOCKED/CLOSED), via the
  Accounting Engine's own pre-existing `lock_period()` method, called
  unchanged by this module's `approve_close()`. See the module README's
  "Architecture" section for exactly why there is no second period
  system here, even though the word "closed" appears in both places.
"""
from enum import Enum


class PeriodCloseStatus(str, Enum):
    REQUESTED = "REQUESTED"            # maker asked for close; controls just evaluated
    READY_FOR_CLOSE = "READY_FOR_CLOSE"  # every blocking control passed
    CONTROLS_FAILED = "CONTROLS_FAILED"  # at least one blocking control failed
    CLOSED = "CLOSED"                  # terminal — checker approved; accounting period is now LOCKED
    REJECTED = "REJECTED"              # terminal — checker declined; rework means a new process


class ControlStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"            # visible, does not block by default — see README
    NOT_APPLICABLE = "NOT_APPLICABLE"  # e.g. no evidence was required for this close


class ControlName(str, Enum):
    PERIOD_INTEGRITY = "PERIOD_INTEGRITY"
    TRIAL_BALANCE_BALANCED = "TRIAL_BALANCE_BALANCED"
    UNPOSTED_JOURNALS = "UNPOSTED_JOURNALS"
    RECONCILIATION_EXCEPTIONS = "RECONCILIATION_EXCEPTIONS"
    REQUIRED_EVIDENCE = "REQUIRED_EVIDENCE"


class AuditAction(str, Enum):
    CLOSE_CHECK_STARTED = "CLOSE_CHECK_STARTED"
    CLOSE_CHECK_COMPLETED = "CLOSE_CHECK_COMPLETED"
    CLOSE_REQUESTED = "CLOSE_REQUESTED"
    CLOSE_CONTROL_FAILED = "CLOSE_CONTROL_FAILED"
    CLOSE_REVIEWED = "CLOSE_REVIEWED"
    CLOSE_APPROVED = "CLOSE_APPROVED"
    CLOSE_REJECTED = "CLOSE_REJECTED"
    PERIOD_CLOSED = "PERIOD_CLOSED"
    # No PERIOD_LOCKED here: locking the authoritative AccountingPeriod
    # is done by calling accounting.lock_period() unchanged, which
    # already logs its own PERIOD_LOCKED event under the Accounting
    # Engine's own AuditAction — duplicating it here would create two
    # audit entries for one real action. See README "Audit events".
    # No POST_CLOSE_ADJUSTMENT_REQUESTED: post-close adjustments are
    # not implemented — see README "Post-close adjustments".
