"""
Domain models for Period Close & Financial Controls.

`CloseReadinessReport` and `ControlFinding` are never persisted — like
every Financial Reporting report, they are computed fresh on every
call to `check_close_readiness`. `PeriodCloseProcess` IS persisted
(see repository/) because it is a genuine multi-step workflow record
that must survive between the maker's request and the checker's later
review/approval, in separate calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .enums import ControlName, ControlStatus, PeriodCloseStatus


@dataclass
class ControlFinding:
    control: ControlName
    status: ControlStatus
    blocking: bool
    message: str
    reference: dict = field(default_factory=dict)


@dataclass
class CloseReadinessReport:
    org_id: str
    period_id: str
    generated_at: datetime
    generated_by: str
    findings: List[ControlFinding]
    is_ready: bool
    blocking_failures: List[ControlName]


@dataclass
class PeriodCloseProcess:
    id: str
    org_id: str
    period_id: str
    status: PeriodCloseStatus
    requested_by: str
    requested_at: datetime
    # Snapshot of the readiness check taken at request time (and
    # refreshed by recheck_controls) — findings as plain dicts so this
    # record has no import-time dependency on the report dataclasses'
    # exact shape evolving; see services/service.py::_findings_to_dicts.
    last_findings: List[dict] = field(default_factory=list)
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    supersedes_close_process_id: Optional[str] = None
