"""
Pure state-transition rules for Finding and Remediation. No side
effects, no storage dependency — same discipline as every other
module's domain/rules.py.
"""
from __future__ import annotations

from .enums import FindingStatus, RemediationStatus
from .errors import InvalidFindingStateError, InvalidRemediationStateError

# CLOSED is terminal within this table — reopening is a separate,
# explicit, audited method (`reopen_finding`) that intentionally
# bypasses this table rather than being just another row in it, so it
# can never be reached by an ordinary status-transition call.
FINDING_TRANSITIONS: dict[FindingStatus, frozenset[FindingStatus]] = {
    FindingStatus.OPEN: frozenset({FindingStatus.UNDER_REVIEW}),
    FindingStatus.UNDER_REVIEW: frozenset({
        FindingStatus.REMEDIATION_REQUIRED, FindingStatus.RESOLVED, FindingStatus.OPEN,
    }),
    FindingStatus.REMEDIATION_REQUIRED: frozenset({FindingStatus.RESOLVED}),
    FindingStatus.RESOLVED: frozenset({
        FindingStatus.VERIFIED, FindingStatus.REMEDIATION_REQUIRED,
    }),
    FindingStatus.VERIFIED: frozenset({FindingStatus.CLOSED}),
    FindingStatus.CLOSED: frozenset(),
}

REMEDIATION_TRANSITIONS: dict[RemediationStatus, frozenset[RemediationStatus]] = {
    RemediationStatus.PLANNED: frozenset({RemediationStatus.IN_PROGRESS}),
    RemediationStatus.IN_PROGRESS: frozenset({
        RemediationStatus.COMPLETED, RemediationStatus.PLANNED,
    }),
    RemediationStatus.COMPLETED: frozenset({
        RemediationStatus.VERIFIED, RemediationStatus.IN_PROGRESS,
    }),
    RemediationStatus.VERIFIED: frozenset(),
}


def assert_finding_transition_allowed(current: FindingStatus, new: FindingStatus) -> None:
    if new not in FINDING_TRANSITIONS.get(current, frozenset()):
        raise InvalidFindingStateError(f"Cannot move a finding from {current.value} to {new.value}.")


def assert_remediation_transition_allowed(current: RemediationStatus, new: RemediationStatus) -> None:
    if new not in REMEDIATION_TRANSITIONS.get(current, frozenset()):
        raise InvalidRemediationStateError(
            f"Cannot move a remediation from {current.value} to {new.value}."
        )
