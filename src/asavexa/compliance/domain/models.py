"""
Domain models for Controls & Compliance / Audit Workspace.

Four distinct persisted entities, deliberately kept separate per the
build brief: a `ControlDefinition` (the reusable, named control) is not
a `ControlExecution` (one run of it) is not a `Finding` (created when
an execution fails) is not a `Remediation` (the tracked fix for a
finding). Conflating any two of these would make "why did this control
fail, and what proves it was fixed" unanswerable — which is the entire
point of this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from .enums import ControlDomain, ControlResult, ControlSeverity, FindingStatus, RemediationStatus


@dataclass
class ControlDefinition:
    """
    A named, reusable control — defined once, executed many times
    against different organisations/periods. `check_key` selects one of
    a fixed set of built-in check functions (see
    services/service.py's `_check_registry` / `_STANDARD_CONTROLS`) —
    there is no generic rule language here, deliberately (Blueprint:
    "do not build a generic rules engine unless genuinely required").
    """
    id: str
    org_id: str
    code: str                  # short, stable, human-referenced: e.g. "ACC-001"
    name: str
    description: str
    objective: str
    severity: ControlSeverity
    domain: ControlDomain
    check_key: str
    created_by: str
    created_at: datetime
    frequency: Optional[str] = None  # descriptive only ("MONTHLY", "PER_PERIOD_CLOSE") — no scheduler
    is_active: bool = True


@dataclass
class ControlExecution:
    """
    One run of a ControlDefinition. `result`, `explanation`, and
    `reference` are set once at creation and never edited afterward —
    re-evaluating a control means creating a new ControlExecution, not
    mutating an old one (the same "never silently convert FAIL to PASS"
    discipline the build brief asked for, enforced by there being no
    method that could). `reviewed_by`/`reviewed_at` is a separate,
    later checkpoint — recording that someone looked at this result,
    not changing what it says.
    """
    id: str
    org_id: str
    control_id: str
    executed_by: str
    executed_at: datetime
    result: ControlResult
    explanation: str
    reference: dict = field(default_factory=dict)
    period_id: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    finding_id: Optional[str] = None


@dataclass
class Finding:
    """
    Created when a ControlExecution's result requires one (FAIL, or
    REQUIRES_REVIEW at the caller's discretion — see
    services/service.py::create_finding_from_execution). Never
    silently hidden: a finding is closed only through
    RESOLVED -> VERIFIED -> CLOSED, each an explicit, permissioned,
    audited call.
    """
    id: str
    org_id: str
    control_id: str
    execution_id: str
    description: str
    severity: ControlSeverity
    status: FindingStatus
    created_by: str
    created_at: datetime
    evidence_ref: Optional[str] = None
    remediation_id: Optional[str] = None
    closed_by: Optional[str] = None
    closed_at: Optional[datetime] = None
    # Every status change and reopen, oldest first — never overwritten,
    # only appended to. Same belt-and-suspenders pattern as
    # Reconciliation's BankTransaction.match_history.
    history: List[dict] = field(default_factory=list)


@dataclass
class Remediation:
    """
    The tracked fix for exactly one Finding — not a general task/ticket
    system (Blueprint: "do not build project-management functionality").
    `owner` completes it (COMPLETED); a *different* permission
    (`finding:verify`, enforced at the API boundary, never by comparing
    actor strings here) is required to move it to VERIFIED, which is
    the only thing that lets the parent Finding reach VERIFIED/CLOSED.
    """
    id: str
    org_id: str
    finding_id: str
    action: str
    owner: str
    status: RemediationStatus
    created_by: str
    created_at: datetime
    due_date: Optional[date] = None
    completion_evidence_ref: Optional[str] = None
    completed_by: Optional[str] = None
    completed_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    verification_note: Optional[str] = None
