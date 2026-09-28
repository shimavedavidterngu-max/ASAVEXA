"""
Enumerations for Controls & Compliance / Audit Workspace.

Signature principle: "Don't just report the number. Prove it."
Extended here to: "Don't just claim compliance. Prove the control."

This module makes NO regulatory claims (no "IFRS compliant", no "SOX
compliant") — it provides infrastructure for documenting controls,
executing them against the six authoritative modules, recording
findings, and tracking remediation to verified closure. What any of
that means against a specific external standard is a judgement for the
organisation's own auditors, not a string this code prints.
"""
from enum import Enum


class ControlDomain(str, Enum):
    """Which authoritative module a control evaluates. Every check this
    module runs calls into exactly one of these — never recomputes
    their logic."""
    ACCOUNTING = "ACCOUNTING"
    RECONCILIATION = "RECONCILIATION"
    EVIDENCE = "EVIDENCE"
    REPORTING = "REPORTING"
    PERIOD_CLOSE = "PERIOD_CLOSE"


class ControlSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ControlResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    REMEDIATION_REQUIRED = "REMEDIATION_REQUIRED"
    RESOLVED = "RESOLVED"          # remediation done, awaiting independent verification
    VERIFIED = "VERIFIED"          # a different actor confirmed the remediation
    CLOSED = "CLOSED"              # terminal — reopening is a separate, explicit, audited action


class RemediationStatus(str, Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"        # owner says done; not yet independently verified
    VERIFIED = "VERIFIED"          # terminal


class AuditAction(str, Enum):
    CONTROL_DEFINED = "CONTROL_DEFINED"
    CONTROL_DEACTIVATED = "CONTROL_DEACTIVATED"
    CONTROL_EXECUTED = "CONTROL_EXECUTED"
    CONTROL_REVIEWED = "CONTROL_REVIEWED"
    FINDING_CREATED = "FINDING_CREATED"
    FINDING_STATUS_CHANGED = "FINDING_STATUS_CHANGED"
    FINDING_REOPENED = "FINDING_REOPENED"
    REMEDIATION_CREATED = "REMEDIATION_CREATED"
    REMEDIATION_STARTED = "REMEDIATION_STARTED"
    REMEDIATION_COMPLETED = "REMEDIATION_COMPLETED"
    REMEDIATION_REJECTED = "REMEDIATION_REJECTED"
    REMEDIATION_VERIFIED = "REMEDIATION_VERIFIED"
    FINDING_CLOSED = "FINDING_CLOSED"
    # No separate CONTROL_PASSED/CONTROL_FAILED: the result is carried
    # as a field on the one CONTROL_EXECUTED event, exactly like
    # Reporting logs one REPORT_GENERATED event carrying is_balanced
    # rather than separate BALANCED/UNBALANCED actions. Two audit rows
    # for one action would be duplication, not thoroughness.
