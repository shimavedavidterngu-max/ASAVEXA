from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from ...period_close.domain.enums import ControlName, ControlStatus, PeriodCloseStatus


class RequestCloseRequest(BaseModel):
    required_evidence_refs: Optional[List[str]] = None


class ControlFindingOut(BaseModel):
    control: ControlName
    status: ControlStatus
    blocking: bool
    message: str
    reference: dict

    model_config = {"from_attributes": True}


class CloseReadinessReportOut(BaseModel):
    org_id: str
    period_id: str
    generated_at: datetime
    generated_by: str
    findings: List[ControlFindingOut]
    is_ready: bool
    blocking_failures: List[ControlName]

    model_config = {"from_attributes": True}


class PeriodCloseProcessOut(BaseModel):
    id: str
    org_id: str
    period_id: str
    status: PeriodCloseStatus
    requested_by: str
    requested_at: datetime
    last_findings: list
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    rejected_by: Optional[str]
    rejected_at: Optional[datetime]
    rejection_reason: Optional[str]
    supersedes_close_process_id: Optional[str]

    model_config = {"from_attributes": True}


class ApproveCloseRequest(BaseModel):
    reason: Optional[str] = None


class RejectCloseRequest(BaseModel):
    reason: str
