from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ...evidence.domain.enums import EvidenceType
from ...evidence.services.vault import EvidenceVault
from ...identity.domain.permissions import EVIDENCE_READ, EVIDENCE_UPLOAD, EVIDENCE_VERIFY
from ..deps import get_current_actor, get_current_org, get_evidence_vault, require_permission
from ..schemas.evidence import (
    EvidenceOut,
    EvidenceStatusForReferenceOut,
    RejectEvidenceRequest,
    VerifyEvidenceRequest,
)

router = APIRouter(prefix="/evidence", tags=["Evidence Vault"])


@router.post(
    "", response_model=EvidenceOut, status_code=201,
    dependencies=[Depends(require_permission(EVIDENCE_UPLOAD))],
)
async def upload_evidence(
    file: UploadFile = File(...),
    type: EvidenceType = Form(...),
    linked_journal_id: Optional[str] = Form(None),
    linked_transaction_ref: Optional[str] = Form(None),
    allow_duplicate: bool = Form(False),
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    vault: EvidenceVault = Depends(get_evidence_vault),
):
    content = await file.read()
    return vault.upload_evidence(
        org_id=org_id, type=type, content=content, original_filename=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream", uploaded_by=actor,
        linked_journal_id=linked_journal_id, linked_transaction_ref=linked_transaction_ref,
        allow_duplicate=allow_duplicate,
    )


@router.get("", response_model=list[EvidenceOut], dependencies=[Depends(require_permission(EVIDENCE_READ))])
def list_evidence(
    org_id: str = Depends(get_current_org),
    vault: EvidenceVault = Depends(get_evidence_vault),
):
    return vault.list_for_org(org_id)


@router.get(
    "/status", response_model=EvidenceStatusForReferenceOut,
    dependencies=[Depends(require_permission(EVIDENCE_READ))],
)
def get_status_for_reference(
    journal_id: Optional[str] = None,
    transaction_ref: Optional[str] = None,
    org_id: str = Depends(get_current_org),
    vault: EvidenceVault = Depends(get_evidence_vault),
):
    """The API-level implementation of 'Show Me the Number': given a
    journal id (or transaction ref), returns its evidence status, or
    the literal MISSING sentinel if nothing has been linked yet."""
    status = vault.get_status_for_reference(org_id, journal_id=journal_id, transaction_ref=transaction_ref)
    return EvidenceStatusForReferenceOut(status=status)


@router.get("/{evidence_id}", response_model=EvidenceOut, dependencies=[Depends(require_permission(EVIDENCE_READ))])
def get_evidence(
    evidence_id: str,
    org_id: str = Depends(get_current_org),
    vault: EvidenceVault = Depends(get_evidence_vault),
):
    return vault.get_evidence(org_id, evidence_id)


@router.post(
    "/{evidence_id}/verify", response_model=EvidenceOut,
    dependencies=[Depends(require_permission(EVIDENCE_VERIFY))],
)
def verify_evidence(
    evidence_id: str,
    body: VerifyEvidenceRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    vault: EvidenceVault = Depends(get_evidence_vault),
):
    return vault.verify_evidence(org_id, evidence_id, actor=actor, note=body.note)


@router.post(
    "/{evidence_id}/reject", response_model=EvidenceOut,
    dependencies=[Depends(require_permission(EVIDENCE_VERIFY))],
)
def reject_evidence(
    evidence_id: str,
    body: RejectEvidenceRequest,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    vault: EvidenceVault = Depends(get_evidence_vault),
):
    return vault.reject_evidence(org_id, evidence_id, actor=actor, reason=body.reason)
