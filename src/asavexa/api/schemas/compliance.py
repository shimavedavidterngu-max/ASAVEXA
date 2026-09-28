from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from ...compliance.domain.enums import ControlDomain, ControlResult, ControlSeverity, FindingStatus, RemediationStatus


class DefineControlRequest(BaseModel):
    code: str
    name: str
    description: str
    objective: str
    severity: ControlSeverity
    domain: ControlDomain
    check_key: str
    frequency: Optional[str] = None


class ControlDefinitionOut(BaseModel):
    id: str
    org_id: str
    code: str
    name: str
    description: str
    objective: str
    severity: ControlSeverity
    domain: ControlDomain
    check_key: str
    frequency: Optional[str]
    is_active: bool
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecuteControlRequest(BaseModel):
    period_id: Optional[str] = None
    params: dict = {}


class ControlExecutionOut(BaseModel):
    id: str
    org_id: str
    control_id: str
    period_id: Optional[str]
    executed_by: str
    executed_at: datetime
    result: ControlResult
    explanation: str
    reference: dict
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    finding_id: Optional[str]

    model_config = {"from_attributes": True}


class CreateFindingRequest(BaseModel):
    description: Optional[str] = None


class FindingOut(BaseModel):
    id: str
    org_id: str
    control_id: str
    execution_id: str
    description: str
    severity: ControlSeverity
    status: FindingStatus
    created_by: str
    created_at: datetime
    evidence_ref: Optional[str]
    remediation_id: Optional[str]
    closed_by: Optional[str]
    closed_at: Optional[datetime]
    history: list

    model_config = {"from_attributes": True}


class FindingTransitionRequest(BaseModel):
    reason: Optional[str] = None


class RequiredReasonRequest(BaseModel):
    """Distinct from FindingTransitionRequest: for the two endpoints
    (send-back-to-open, mark-resolved-without-remediation) where the
    service layer treats a reason as mandatory, not optional — reusing
    the optional schema there would let a client silently omit it."""
    reason: str


class ReopenFindingRequest(BaseModel):
    reason: str


class CreateRemediationRequest(BaseModel):
    action: str
    owner: str
    due_date: Optional[date] = None


class RemediationOut(BaseModel):
    id: str
    org_id: str
    finding_id: str
    action: str
    owner: str
    status: RemediationStatus
    created_by: str
    created_at: datetime
    due_date: Optional[date]
    completion_evidence_ref: Optional[str]
    completed_by: Optional[str]
    completed_at: Optional[datetime]
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    verification_note: Optional[str]

    model_config = {"from_attributes": True}


class CompleteRemediationRequest(BaseModel):
    completion_evidence_ref: Optional[str] = None


class VerifyRemediationRequest(BaseModel):
    note: Optional[str] = None


class RejectRemediationRequest(BaseModel):
    reason: str
