"""
EvidenceVault — the public service facade for the Evidence Vault module.

Per its own integration-contract README (written when the Accounting
Engine was built): this module never validates a journal's balance and
the Accounting Engine never validates evidence content. The two connect
only through opaque string references (`Journal.evidence_ref` /
`EvidenceRecord.linked_journal_id`) — neither module imports the
other's domain types.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from ...audit.models import AuditEvent
from ...audit.repository import AuditRepository
from ..domain import rules
from ..domain.enums import AuditAction, EvidenceStatus, EvidenceType
from ..domain.errors import DuplicateEvidenceError, EvidenceNotFoundError
from ..domain.models import EvidenceRecord
from ..repository.interfaces import EvidenceRepository

MISSING = "MISSING"  # sentinel per Blueprint Rule 2: "clearly show MISSING EVIDENCE"


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceVault:
    def __init__(self, evidence: EvidenceRepository, audit: AuditRepository):
        self.evidence = evidence
        self.audit = audit

    # ------------------------------------------------------------------
    def upload_evidence(
        self,
        org_id: str,
        type: EvidenceType,
        content: bytes,
        original_filename: str,
        content_type: str,
        uploaded_by: str,
        linked_journal_id: Optional[str] = None,
        linked_transaction_ref: Optional[str] = None,
        metadata: Optional[dict] = None,
        allow_duplicate: bool = False,
    ) -> EvidenceRecord:
        file_hash = rules.compute_file_hash(content)

        existing = self.evidence.get_by_hash(org_id, file_hash)
        if existing is not None and not allow_duplicate:
            raise DuplicateEvidenceError(
                f"Identical content already uploaded as evidence {existing.id} "
                f"({existing.original_filename}). Pass allow_duplicate=True if this "
                f"is intentional (e.g. a supplier re-sending the same document)."
            )

        record = EvidenceRecord(
            id=_new_id(), org_id=org_id, type=type, status=EvidenceStatus.UPLOADED,
            file_hash=file_hash, original_filename=original_filename,
            content_type=content_type, size_bytes=len(content), uploaded_by=uploaded_by,
            uploaded_at=_now(), linked_journal_id=linked_journal_id,
            linked_transaction_ref=linked_transaction_ref, metadata=metadata or {},
        )
        self.evidence.create(record)
        self._log(
            AuditAction.EVIDENCE_UPLOADED, uploaded_by, record.id, org_id,
            new_value={
                "type": type.value, "filename": original_filename,
                "hash": file_hash, "linked_journal_id": linked_journal_id,
            },
        )
        return record

    def _get(self, org_id: str, evidence_id: str) -> EvidenceRecord:
        record = self.evidence.get(org_id, evidence_id)
        if record is None:
            raise EvidenceNotFoundError(f"Evidence {evidence_id} not found.")
        return record

    def set_status(
        self,
        org_id: str,
        evidence_id: str,
        new_status: EvidenceStatus,
        actor: str,
        note: Optional[str] = None,
    ) -> EvidenceRecord:
        record = self._get(org_id, evidence_id)
        rules.assert_transition_allowed(record.status, new_status)
        previous_status = record.status.value
        record.status = new_status
        if new_status == EvidenceStatus.VERIFIED:
            record.verified_by = actor
            record.verified_at = _now()
            record.verification_note = note
        if new_status == EvidenceStatus.REJECTED:
            record.rejection_reason = note
        self.evidence.update(record)
        self._log(
            AuditAction.EVIDENCE_STATUS_CHANGED, actor, record.id, org_id,
            previous_value={"status": previous_status}, new_value={"status": new_status.value},
            reason=note,
        )
        return record

    def verify_evidence(self, org_id: str, evidence_id: str, actor: str, note: Optional[str] = None) -> EvidenceRecord:
        record = self.set_status(org_id, evidence_id, EvidenceStatus.VERIFIED, actor, note)
        self._log(AuditAction.EVIDENCE_VERIFIED, actor, record.id, org_id, reason=note)
        return record

    def reject_evidence(self, org_id: str, evidence_id: str, actor: str, reason: str) -> EvidenceRecord:
        record = self.set_status(org_id, evidence_id, EvidenceStatus.REJECTED, actor, reason)
        self._log(AuditAction.EVIDENCE_REJECTED, actor, record.id, org_id, reason=reason)
        return record

    def get_evidence(self, org_id: str, evidence_id: str) -> EvidenceRecord:
        return self._get(org_id, evidence_id)

    def list_for_org(self, org_id: str) -> List[EvidenceRecord]:
        return self.evidence.list_for_org(org_id)

    def get_status_for_reference(
        self, org_id: str, journal_id: Optional[str] = None, transaction_ref: Optional[str] = None
    ) -> str:
        """
        Blueprint Rule 2: "if evidence is unavailable, clearly show
        MISSING EVIDENCE." Returns the MISSING sentinel when no evidence
        record is linked to the given journal/transaction, otherwise the
        record's actual status value.
        """
        record = None
        if journal_id is not None:
            record = self.evidence.find_for_journal(org_id, journal_id)
        if record is None and transaction_ref is not None:
            record = self.evidence.find_for_transaction_ref(org_id, transaction_ref)
        return record.status.value if record is not None else MISSING

    # ------------------------------------------------------------------
    def _log(
        self,
        action: AuditAction,
        actor: str,
        entity_id: str,
        org_id: str,
        previous_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.audit.record(
            AuditEvent(
                id=_new_id(), org_id=org_id, entity_type="EvidenceRecord", entity_id=entity_id,
                action=action.value, actor=actor, timestamp=_now(),
                previous_value=previous_value, new_value=new_value, reason=reason,
            )
        )
