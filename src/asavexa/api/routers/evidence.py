from typing import Optional

import os
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from ...evidence.domain.enums import EvidenceType
from ...evidence.services.vault import EvidenceVault
from ...identity.domain.permissions import EVIDENCE_READ, EVIDENCE_UPLOAD, EVIDENCE_VERIFY
from ...security.context import SecurityContext
from ..deps import get_current_actor, get_current_org, get_evidence_vault, get_security, require_permission
from ..schemas.evidence import (
    EvidenceOut,
    EvidenceStatusForReferenceOut,
    RejectEvidenceRequest,
    VerifyEvidenceRequest,
)

router = APIRouter(prefix="/evidence", tags=["Evidence Vault"])


def _max_upload_bytes() -> int:
    """Evidence files are capped (default 25 MB, ASAVEXA_MAX_UPLOAD_MB to change) so one upload cannot exhaust memory or storage."""
    try:
        return max(1, int(os.environ.get("ASAVEXA_MAX_UPLOAD_MB", "25"))) * 1024 * 1024
    except ValueError:
        return 25 * 1024 * 1024


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
    limit = _max_upload_bytes()
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=f"This file is larger than the {limit // (1024 * 1024)} MB limit for evidence files.")
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
    record = vault.find_record_for_reference(org_id, journal_id=journal_id, transaction_ref=transaction_ref)
    if record is None:
        return EvidenceStatusForReferenceOut(status=vault.get_status_for_reference(org_id, journal_id=journal_id, transaction_ref=transaction_ref))
    return EvidenceStatusForReferenceOut(status=record.status.value, evidence_id=record.id)


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


@router.get("/{evidence_id}/storage", dependencies=[Depends(require_permission(EVIDENCE_READ))])
def get_storage_info(
    evidence_id: str,
    org_id: str = Depends(get_current_org),
    vault: EvidenceVault = Depends(get_evidence_vault),
):
    """Whether the file itself is stored (encrypted), and where. Never returns a key."""
    info = vault.content_info(org_id, evidence_id)
    return {"stored": info is not None, "info": info}


@router.get("/{evidence_id}/content", dependencies=[Depends(require_permission(EVIDENCE_READ))])
def download_content(
    evidence_id: str,
    org_id: str = Depends(get_current_org),
    actor: str = Depends(get_current_actor),
    vault: EvidenceVault = Depends(get_evidence_vault),
    security: SecurityContext = Depends(get_security),
):
    """The decrypted original, checked against its fingerprint. Always sent as a download (never rendered by the
    browser) and every download is written to the audit trail."""
    record = vault.get_evidence(org_id, evidence_id)
    data = vault.read_content(org_id, evidence_id)
    security.log("EVIDENCE_DOWNLOADED", actor, evidence_id, org_id=org_id, entity_type="EvidenceRecord", reason=f"{len(data)} bytes")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", record.original_filename or "evidence")[:120] or "evidence"
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"', "X-Content-Type-Options": "nosniff"})
