"""
PostgreSQL/SQLAlchemy implementation of the Evidence Vault repository.
Implements the same Protocol as evidence/repository/sqlite_repository.py.
Not executed in the sandbox that produced this starter codebase.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...evidence.domain.enums import EvidenceStatus, EvidenceType
from ...evidence.domain.models import EvidenceRecord
from .evidence_models import EvidenceRecordORM


def _row_to_domain(row: EvidenceRecordORM) -> EvidenceRecord:
    return EvidenceRecord(
        id=row.id, org_id=row.org_id, type=EvidenceType(row.type), status=EvidenceStatus(row.status),
        file_hash=row.file_hash, original_filename=row.original_filename, content_type=row.content_type,
        size_bytes=row.size_bytes, uploaded_by=row.uploaded_by, uploaded_at=row.uploaded_at,
        verified_by=row.verified_by, verified_at=row.verified_at, verification_note=row.verification_note,
        rejection_reason=row.rejection_reason, linked_journal_id=row.linked_journal_id,
        linked_transaction_ref=row.linked_transaction_ref, metadata=row.metadata_json or {},
    )


class SqlAlchemyEvidenceRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: EvidenceRecord) -> EvidenceRecord:
        row = EvidenceRecordORM(
            id=record.id, org_id=record.org_id, type=record.type.value, status=record.status.value,
            file_hash=record.file_hash, original_filename=record.original_filename,
            content_type=record.content_type, size_bytes=record.size_bytes,
            uploaded_by=record.uploaded_by, uploaded_at=record.uploaded_at,
            linked_journal_id=record.linked_journal_id, linked_transaction_ref=record.linked_transaction_ref,
            metadata_json=record.metadata or {},
        )
        self.session.add(row)
        return record

    def get(self, org_id: str, evidence_id: str) -> Optional[EvidenceRecord]:
        row = self.session.get(EvidenceRecordORM, evidence_id)
        if row is None or row.org_id != org_id:
            return None
        return _row_to_domain(row)

    def get_by_hash(self, org_id: str, file_hash: str) -> Optional[EvidenceRecord]:
        row = self.session.scalar(
            select(EvidenceRecordORM).where(
                EvidenceRecordORM.org_id == org_id, EvidenceRecordORM.file_hash == file_hash
            )
        )
        return _row_to_domain(row) if row else None

    def update(self, record: EvidenceRecord) -> EvidenceRecord:
        row = self.session.get(EvidenceRecordORM, record.id)
        row.status = record.status.value
        row.verified_by = record.verified_by
        row.verified_at = record.verified_at
        row.verification_note = record.verification_note
        row.rejection_reason = record.rejection_reason
        row.linked_journal_id = record.linked_journal_id
        row.linked_transaction_ref = record.linked_transaction_ref
        row.metadata_json = record.metadata or {}
        return record

    def list_for_org(self, org_id: str) -> List[EvidenceRecord]:
        rows = self.session.scalars(
            select(EvidenceRecordORM).where(EvidenceRecordORM.org_id == org_id).order_by(EvidenceRecordORM.uploaded_at)
        ).all()
        return [_row_to_domain(r) for r in rows]

    def find_for_journal(self, org_id: str, journal_id: str) -> Optional[EvidenceRecord]:
        row = self.session.scalar(
            select(EvidenceRecordORM)
            .where(EvidenceRecordORM.org_id == org_id, EvidenceRecordORM.linked_journal_id == journal_id)
            .order_by(EvidenceRecordORM.uploaded_at.desc())
        )
        return _row_to_domain(row) if row else None

    def find_for_transaction_ref(self, org_id: str, transaction_ref: str) -> Optional[EvidenceRecord]:
        row = self.session.scalar(
            select(EvidenceRecordORM)
            .where(EvidenceRecordORM.org_id == org_id, EvidenceRecordORM.linked_transaction_ref == transaction_ref)
            .order_by(EvidenceRecordORM.uploaded_at.desc())
        )
        return _row_to_domain(row) if row else None
