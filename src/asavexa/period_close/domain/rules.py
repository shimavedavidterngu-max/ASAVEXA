"""
Pure state-transition rules for PeriodCloseProcess. No side effects, no
storage dependency — same discipline as every other module's
domain/rules.py.
"""
from __future__ import annotations

from .enums import PeriodCloseStatus
from .errors import InvalidCloseStateError

# CLOSED and REJECTED are both fully terminal — rework after REJECTED
# means a brand new PeriodCloseProcess (supersedes_close_process_id),
# never reopening this one. This mirrors Reconciliation's
# ReconciliationStatus exactly.
TRANSITIONS: dict[PeriodCloseStatus, frozenset[PeriodCloseStatus]] = {
    PeriodCloseStatus.REQUESTED: frozenset({
        PeriodCloseStatus.READY_FOR_CLOSE, PeriodCloseStatus.CONTROLS_FAILED,
    }),
    PeriodCloseStatus.CONTROLS_FAILED: frozenset({
        PeriodCloseStatus.READY_FOR_CLOSE, PeriodCloseStatus.CONTROLS_FAILED,
        PeriodCloseStatus.REJECTED,
    }),
    PeriodCloseStatus.READY_FOR_CLOSE: frozenset({
        PeriodCloseStatus.CLOSED, PeriodCloseStatus.REJECTED, PeriodCloseStatus.CONTROLS_FAILED,
    }),
    PeriodCloseStatus.CLOSED: frozenset(),
    PeriodCloseStatus.REJECTED: frozenset(),
}


def assert_transition_allowed(current: PeriodCloseStatus, new: PeriodCloseStatus) -> None:
    if new not in TRANSITIONS.get(current, frozenset()):
        raise InvalidCloseStateError(
            f"Cannot move a period-close process from {current.value} to {new.value}."
        )
