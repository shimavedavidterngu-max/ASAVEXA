from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from ...evidence.domain.enums import EvidenceStatus, EvidenceType


class EvidenceOut(BaseModel):
    id: str
    org_id: str
    type: EvidenceType
    status: EvidenceStatus
    file_hash: str
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_by: str
    uploaded_at: datetime
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    verification_note: Optional[str]
    rejection_reason: Optional[str]
    linked_journal_id: Optional[str]
    linked_transaction_ref: Optional[str]
    metadata: dict

    model_config = {"from_attributes": True}


class VerifyEvidenceRequest(BaseModel):
    note: Optional[str] = None


class RejectEvidenceRequest(BaseModel):
    reason: str


class EvidenceStatusForReferenceOut(BaseModel):
    status: str  # "MISSING" or an EvidenceStatus value
    evidence_id: Optional[str] = None  # the linked record, when there is one
